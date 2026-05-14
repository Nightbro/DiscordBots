import asyncio
import logging
from collections import deque

import discord
from discord.ext import commands

from utils.config import MAX_QUEUE
from utils.guild_state import GuildState, Track

log = logging.getLogger(__name__)

_FFMPEG_STREAM_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}
_FFMPEG_FILE_OPTS = {'options': '-vn'}


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
            return
        track = state.queue.popleft()
        state.current_track = track
        source = _make_source(track)

        def after(error: Exception | None) -> None:
            if error:
                log.error('Playback error in guild %s: %s', self._guild_id, error)
            asyncio.run_coroutine_threadsafe(self.play_next(), self._bot.loop)

        state.voice_client.play(source, after=after)

    async def interrupt(self, track: Track) -> None:
        """Play track immediately, pausing current playback. Resumes after interrupt finishes."""
        state = self._state
        if not state.voice_client or not state.voice_client.is_connected():
            return

        was_playing = state.voice_client.is_playing()
        interrupted = state.current_track if was_playing else None

        if was_playing:
            state.voice_client.pause()

        source = _make_source(track)

        def after(error: Exception | None) -> None:
            if error:
                log.error('Interrupt playback error in guild %s: %s', self._guild_id, error)
            if interrupted:
                # Re-queue at front so it restarts after the interrupt
                state.queue.appendleft(interrupted)
            asyncio.run_coroutine_threadsafe(self.play_next(), self._bot.loop)

        # stop() triggers the original after-callback, which schedules play_next.
        # But play_next guards on is_playing(), and by the time the event loop
        # processes it, our new play() call below will have started — so it exits early.
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
        if state.voice_client:
            state.voice_client.stop()
        state.current_track = None

    async def pause(self) -> None:
        vc = self.voice_client
        if vc and vc.is_playing():
            vc.pause()

    async def resume(self) -> None:
        vc = self.voice_client
        if vc and vc.is_paused():
            vc.resume()

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
    if track.file_path and track.file_path.exists():
        return discord.FFmpegPCMAudio(str(track.file_path), **_FFMPEG_FILE_OPTS)
    return discord.FFmpegPCMAudio(track.url, **_FFMPEG_STREAM_OPTS)
