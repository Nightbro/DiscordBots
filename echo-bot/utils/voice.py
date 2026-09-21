import asyncio
import logging
import tempfile
import time
from collections import deque

import discord
from discord.ext import commands

from utils import devlog
from utils.config import MAX_QUEUE
from utils.downloader import Downloader
from utils.guild_state import GuildState, Track
from utils.message import MessageWriter

log = logging.getLogger(__name__)

# FFmpeg option fragments
_FFMPEG_RECONNECT = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
# -loglevel error keeps FFmpeg's stderr empty on a clean run, so anything it
# writes there is a real problem worth reporting (see _report_ffmpeg_errors).
_FFMPEG_AUDIO = '-vn -loglevel error'


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

        # Our tracked vc may be stale (e.g. after a 4006 reconnect or a race between
        # two concurrent on_voice_state_update handlers).  Always reconcile against
        # discord.py's authoritative guild-level voice client first.
        if not (state.voice_client and state.voice_client.is_connected()):
            state.voice_client = channel.guild.voice_client  # may still be None

        if state.voice_client and state.voice_client.is_connected():
            # Already connected — just move to the target channel if needed.
            if state.voice_client.channel.id != channel.id:
                await state.voice_client.move_to(channel)
            return

        # No live connection — connect fresh.
        try:
            vc = await channel.connect()
            state.voice_client = vc
        except discord.ClientException as exc:
            if 'Already connected' in str(exc):
                # Extremely narrow race: another task connected between our check
                # and the connect() call.  Re-sync and treat as already joined.
                log.warning('join: race on connect() — resyncing from guild state')
                existing = channel.guild.voice_client
                if existing:
                    state.voice_client = existing
                else:
                    raise
            else:
                raise

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
        devlog.current_guild.set(self._guild_id)
        track = state.queue.popleft()
        state.current_track = track
        state.last_track = track

        # Download remote tracks before playback; local files (intros, TTS, soundboard) skip this.
        if track.url.startswith('http') and not (track.file_path and track.file_path.exists()):
            try:
                await Downloader.download(track)
            except Exception as exc:
                log.error('Failed to download "%s": %s — skipping', track.title, exc, exc_info=exc)
                await self._send_error_to_channel(track.title, exc)
                asyncio.run_coroutine_threadsafe(self.play_next(), self._bot.loop)
                return

        # Build source using seek_to, then reset it (consumed on use).
        source = _make_source(track)
        state.track_position_secs = track.seek_to
        track.seek_to = 0.0

        def after(error: Exception | None) -> None:
            # Runs on the player thread — pass the guild explicitly for the dev log.
            if error:
                log.error('Playback error in guild %s: %s', self._guild_id, error,
                          extra={'guild_id': self._guild_id})
            _report_ffmpeg_errors(source, track, self._guild_id)
            asyncio.run_coroutine_threadsafe(self.play_next(), self._bot.loop)

        state.track_play_start = time.monotonic()
        state.voice_client.play(source, after=after)

    async def interrupt(self, track: Track) -> None:
        """Play track immediately, pausing current playback. Resumes from exact position after."""
        devlog.current_guild.set(self._guild_id)
        state = self._state
        # Resync from discord.py's guild-level vc if our state is stale — this handles
        # the race where interrupt() is called during join() before state.voice_client is set
        # (e.g. bot's own on_voice_state_update fires while channel.connect() is still awaited).
        if not (state.voice_client and state.voice_client.is_connected()):
            guild = self._bot.get_guild(self._guild_id)
            if guild and guild.voice_client and guild.voice_client.is_connected():
                state.voice_client = guild.voice_client
        if not state.voice_client or not state.voice_client.is_connected():
            log.warning(
                'interrupt(%s): no connected voice client after resync — dropping track "%s"',
                self._guild_id, track.title,
            )
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
                log.error('Interrupt playback error in guild %s: %s', self._guild_id, error,
                          extra={'guild_id': self._guild_id})
            _report_ffmpeg_errors(source, track, self._guild_id)
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
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_error_to_channel(self, track_title: str, exc: Exception) -> None:
        state = self._state
        if not state.last_text_channel_id:
            return
        channel = self._bot.get_channel(state.last_text_channel_id)
        if channel is None:
            return
        try:
            await channel.send(embed=MessageWriter.error(
                f'Download failed — skipping',
                f'**{track_title}**\n{exc}',
            ))
        except Exception as send_exc:
            log.warning('Could not send download error to channel: %s', send_exc)

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
    """Build an FFmpegPCMAudio source, seeking to track.seek_to if non-zero.

    FFmpeg's stderr goes to a temp file (``source.ffmpeg_stderr``) so failures
    that end playback silently — e.g. an unreadable file — can be reported.
    """
    seek = f'-ss {track.seek_to:.3f}' if track.seek_to else None
    stderr = tempfile.TemporaryFile()
    if track.file_path and track.file_path.exists():
        source = discord.FFmpegPCMAudio(
            str(track.file_path),
            before_options=seek,
            options=_FFMPEG_AUDIO,
            stderr=stderr,
        )
    else:
        # Stream: combine optional seek with reconnect flags
        before = f'{seek} {_FFMPEG_RECONNECT}' if seek else _FFMPEG_RECONNECT
        source = discord.FFmpegPCMAudio(
            track.url, before_options=before, options=_FFMPEG_AUDIO, stderr=stderr,
        )
    source.ffmpeg_stderr = stderr
    return source


def _report_ffmpeg_errors(source: discord.AudioSource, track: Track, guild_id: int) -> None:
    """Log whatever FFmpeg wrote to stderr for this source, then close the temp file."""
    stderr = getattr(source, 'ffmpeg_stderr', None)
    if stderr is None:
        return
    try:
        stderr.seek(0)
        output = stderr.read()
        stderr.close()
    except Exception:
        return
    if isinstance(output, bytes) and output.strip():
        text = output.decode('utf-8', 'replace').strip()
        log.warning('FFmpeg reported errors for "%s":\n%s', track.title, text[-1500:],
                    extra={'guild_id': guild_id})
