import asyncio
import logging
import time
from collections import deque

import discord
from discord.ext import commands

from utils.config import MAX_QUEUE
from utils.downloader import Downloader
from utils.guild_state import GuildState, Track

log = logging.getLogger(__name__)

# FFmpeg option fragments
_FFMPEG_RECONNECT = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
_FFMPEG_AUDIO = '-vn'


class VoiceStreamer:
    """Manages all voice interactions for one guild. Stateless — all state lives in GuildState."""

    def __init__(self, bot: commands.Bot, guild_id: int) -> None:
        self._bot = bot
        self._guild_id = guild_id

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def _state(self) -> GuildState:
        return self._bot.get_guild_state(self._guild_id)

    @property
    def voice_client(self) -> discord.VoiceClient | None:
        return self._state.voice_client

    @property
    def is_playing(self) -> bool:
        vc = self.voice_client
        return vc is not None and vc.is_playing()

    @property
    def is_paused(self) -> bool:
        vc = self.voice_client
        return vc is not None and vc.is_paused()

    @property
    def queue(self) -> deque[Track]:
        return self._state.queue

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def join(self, channel: discord.VoiceChannel) -> None:
        state = self._state
        if state.voice_client and state.voice_client.is_connected():
            await state.voice_client.move_to(channel)
        else:
            vc = await channel.connect()
            state.voice_client = vc

    async def leave(self) -> None:
        state = self._state
        if state.voice_client:
            await state.voice_client.disconnect()
            state.voice_client = None
        state.queue.clear()
        state.current_track = None
        state.interrupted_track = None
        state.track_play_start = None
        state.track_position_secs = 0.0

    async def play(self, track: Track) -> None:
        """Enqueue a track and start playback if idle."""
        state = self._state
        if len(state.queue) >= MAX_QUEUE:
            raise ValueError(f'Queue is full ({MAX_QUEUE} tracks maximum)')
        state.queue.append(track)
        if not self.is_playing and not self.is_paused:
            await self.play_next()

    async def play_next(self) -> None:
        """Advance to the next track in the queue. Called recursively via the after-callback."""
        state = self._state
        if not state.queue or not state.voice_client:
            state.current_track = None
            state.track_play_start = None
            state.track_position_secs = 0.0
            return
        track = state.queue.popleft()
        state.current_track = track
        state.last_track = track

        # Download remote tracks before playback; local files (intros, TTS, soundboard) skip this.
        if track.url.startswith('http') and not (track.file_path and track.file_path.exists()):
            try:
                await Downloader.download(track)
            except Exception as exc:
                log.error('Failed to download "%s": %s — skipping', track.title, exc)
                asyncio.run_coroutine_threadsafe(self.play_next(), self._bot.loop)
                return

        # Build source using seek_to, then reset it (consumed on use).
        source = _make_source(track)
        state.track_position_secs = track.seek_to
        track.seek_to = 0.0

        def after(error: Exception | None) -> None:
            if error:
                log.error('Playback error in guild %s: %s', self._guild_id, error)
            asyncio.run_coroutine_threadsafe(self.play_next(), self._bot.loop)

        state.track_play_start = time.monotonic()
        state.voice_client.play(source, after=after)

    async def interrupt(self, track: Track) -> None:
        """Play track immediately, pausing current playback. Resumes from exact position after."""
        state = self._state
        if not state.voice_client or not state.voice_client.is_connected():
            return

        was_playing = state.voice_client.is_playing()
        was_paused = state.voice_client.is_paused()
        interrupted = state.current_track if (was_playing or was_paused) else None

        if interrupted:
            # Stamp the exact playback position so play_next() can seek back to it.
            pos = state.track_position_secs
            if was_playing and state.track_play_start is not None:
                pos += time.monotonic() - state.track_play_start
            interrupted.seek_to = pos
            state.track_play_start = None

        if was_playing:
            state.voice_client.pause()

        source = _make_source(track)

        def after(error: Exception | None) -> None:
            if error:
                log.error('Interrupt playback error in guild %s: %s', self._guild_id, error)
            if track.cleanup_path:
                track.cleanup_path.unlink(missing_ok=True)
            if interrupted:
                state.queue.appendleft(interrupted)
            asyncio.run_coroutine_threadsafe(self.play_next(), self._bot.loop)

        # stop() triggers the original after-callback → play_next(), but by the time
        # it runs on the event loop our new play() call will have started, so it exits early.
        state.voice_client.stop()
        state.voice_client.play(source, after=after)

    async def skip(self) -> Track | None:
        """Skip the current track. Returns the skipped track or None."""
        state = self._state
        if state.voice_client and (self.is_playing or self.is_paused):
            skipped = state.current_track
            state.voice_client.stop()  # triggers after() → play_next()
            return skipped
        return None

    async def stop(self) -> None:
        """Stop playback and clear the queue."""
        state = self._state
        state.queue.clear()
        state.interrupted_track = None
        state.track_play_start = None
        state.track_position_secs = 0.0
        if state.voice_client:
            state.voice_client.stop()
        state.current_track = None

    async def pause(self) -> None:
        """Pause playback, accumulating elapsed time so position is preserved for interrupt."""
        vc = self.voice_client
        if vc and vc.is_playing():
            vc.pause()
            state = self._state
            if state.track_play_start is not None:
                state.track_position_secs += time.monotonic() - state.track_play_start
                state.track_play_start = None

    async def resume(self) -> None:
        """Resume playback, restarting the elapsed-time clock."""
        vc = self.voice_client
        if vc and vc.is_paused():
            vc.resume()
            self._state.track_play_start = time.monotonic()

    async def replay(self) -> Track | None:
        """Restart the current track (or last played track) from the beginning.

        Re-queues the track at the front with seek_to reset to 0, then stops
        current playback so the after-callback fires and play_next() picks it up.
        Returns the track being replayed, or None if there is nothing to replay.
        """
        state = self._state
        track = state.current_track or state.last_track
        if not track or not state.voice_client:
            return None
        track.seek_to = 0.0  # explicit: always restart from the very beginning
        state.queue.appendleft(track)
        if self.is_playing or self.is_paused:
            state.voice_client.stop()  # triggers after-callback → play_next()
        else:
            await self.play_next()
        return track

    # ------------------------------------------------------------------
    # Auto-leave
    # ------------------------------------------------------------------

    @staticmethod
    async def auto_leave_if_empty(
        bot: commands.Bot,
        guild_id: int,
        channel: discord.VoiceChannel,
    ) -> None:
        """Disconnect if no non-bot members remain in the channel."""
        non_bots = [m for m in channel.members if not m.bot]
        if not non_bots:
            await VoiceStreamer(bot, guild_id).leave()


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _make_source(track: Track) -> discord.FFmpegPCMAudio:
    """Build an FFmpegPCMAudio source, seeking to track.seek_to if non-zero."""
    seek = f'-ss {track.seek_to:.3f}' if track.seek_to else None
    if track.file_path and track.file_path.exists():
        return discord.FFmpegPCMAudio(
            str(track.file_path),
            before_options=seek,
            options=_FFMPEG_AUDIO,
        )
    # Stream: combine optional seek with reconnect flags
    before = f'{seek} {_FFMPEG_RECONNECT}' if seek else _FFMPEG_RECONNECT
    return discord.FFmpegPCMAudio(track.url, before_options=before, options=_FFMPEG_AUDIO)
