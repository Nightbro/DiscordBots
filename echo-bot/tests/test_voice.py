import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

import time

from utils.guild_state import GuildState, Track
from utils.voice import VoiceStreamer, _make_source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _streamer(mock_bot, guild_id=123456789) -> VoiceStreamer:
    return VoiceStreamer(mock_bot, guild_id)


def _vc(playing=False, paused=False, connected=True):
    vc = MagicMock(spec=discord.VoiceClient)
    vc.is_playing.return_value = playing
    vc.is_paused.return_value = paused
    vc.is_connected.return_value = connected
    vc.play = MagicMock()
    vc.stop = MagicMock()
    vc.pause = MagicMock()
    vc.resume = MagicMock()
    vc.disconnect = AsyncMock()
    vc.move_to = AsyncMock()
    vc.channel = MagicMock(spec=discord.VoiceChannel)
    return vc


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

def test_is_playing_false_when_no_voice_client(mock_bot, guild_state):
    s = _streamer(mock_bot)
    assert s.is_playing is False


def test_is_playing_delegates_to_vc(mock_bot, guild_state):
    guild_state.voice_client = _vc(playing=True)
    s = _streamer(mock_bot)
    assert s.is_playing is True


def test_is_paused_false_when_no_voice_client(mock_bot, guild_state):
    s = _streamer(mock_bot)
    assert s.is_paused is False


# ---------------------------------------------------------------------------
# join
# ---------------------------------------------------------------------------

async def test_join_connects_when_no_client(mock_bot, guild_state, voice_channel):
    voice_channel.connect = AsyncMock(return_value=_vc())
    s = _streamer(mock_bot)
    await s.join(voice_channel)
    voice_channel.connect.assert_awaited_once()
    assert guild_state.voice_client is not None


async def test_join_moves_when_already_connected(mock_bot, guild_state, voice_channel):
    vc = _vc()
    guild_state.voice_client = vc
    s = _streamer(mock_bot)
    await s.join(voice_channel)
    vc.move_to.assert_awaited_once_with(voice_channel)


async def test_join_skips_move_when_already_in_target_channel(mock_bot, guild_state, voice_channel):
    vc = _vc()
    vc.channel.id = voice_channel.id  # same channel — no move needed
    guild_state.voice_client = vc
    s = _streamer(mock_bot)
    await s.join(voice_channel)
    vc.move_to.assert_not_awaited()
    voice_channel.connect.assert_not_called()


async def test_join_resyncs_stale_state_from_guild(mock_bot, guild_state, voice_channel):
    """State vc is None/stale but guild.voice_client is live — resync, no fresh connect."""
    existing_vc = _vc()
    voice_channel.guild.voice_client = existing_vc  # discord.py knows about this one
    guild_state.voice_client = None                  # our state is stale
    voice_channel.connect = AsyncMock()

    s = _streamer(mock_bot)
    await s.join(voice_channel)

    voice_channel.connect.assert_not_awaited()       # must NOT call connect()
    assert guild_state.voice_client is existing_vc   # state synced
    existing_vc.move_to.assert_awaited_once_with(voice_channel)  # moved to channel


async def test_join_recovers_from_already_connected_race(mock_bot, guild_state, voice_channel):
    """connect() raises 'Already connected' — recover by resyncing from guild state."""
    existing_vc = _vc()
    voice_channel.connect = AsyncMock(
        side_effect=discord.ClientException('Already connected to a voice channel.')
    )
    voice_channel.guild.voice_client = existing_vc
    guild_state.voice_client = None

    s = _streamer(mock_bot)
    await s.join(voice_channel)

    assert guild_state.voice_client is existing_vc  # recovered


# ---------------------------------------------------------------------------
# leave
# ---------------------------------------------------------------------------

async def test_leave_disconnects(mock_bot, guild_state):
    vc = _vc()
    guild_state.voice_client = vc
    s = _streamer(mock_bot)
    await s.leave()
    vc.disconnect.assert_awaited_once()  # save ref before leave() nulls it


async def test_leave_clears_state(mock_bot, guild_state, sample_track):
    guild_state.voice_client = _vc()
    guild_state.queue.append(sample_track)
    guild_state.current_track = sample_track
    guild_state.interrupted_track = sample_track
    s = _streamer(mock_bot)
    await s.leave()
    assert guild_state.voice_client is None
    assert len(guild_state.queue) == 0
    assert guild_state.current_track is None
    assert guild_state.interrupted_track is None


async def test_leave_noop_when_no_client(mock_bot, guild_state):
    s = _streamer(mock_bot)
    await s.leave()  # should not raise


# ---------------------------------------------------------------------------
# play / play_next
# ---------------------------------------------------------------------------

async def test_play_appends_to_queue(mock_bot, guild_state, sample_track):
    guild_state.voice_client = _vc(playing=True)
    s = _streamer(mock_bot)
    await s.play(sample_track)
    assert sample_track in guild_state.queue


async def test_play_raises_when_queue_full(mock_bot, guild_state):
    from utils.config import MAX_QUEUE
    guild_state.voice_client = _vc(playing=True)
    for i in range(MAX_QUEUE):
        guild_state.queue.append(Track(title=str(i), url='u'))
    s = _streamer(mock_bot)
    with pytest.raises(ValueError, match='Queue is full'):
        await s.play(Track(title='overflow', url='u'))


async def test_play_next_empty_queue_clears_current(mock_bot, guild_state, sample_track):
    guild_state.voice_client = _vc()
    guild_state.current_track = sample_track
    s = _streamer(mock_bot)
    await s.play_next()
    assert guild_state.current_track is None


async def test_play_next_plays_from_queue(mock_bot, guild_state, sample_track):
    vc = _vc()
    guild_state.voice_client = vc
    guild_state.queue.append(sample_track)
    s = _streamer(mock_bot)
    with patch('utils.voice._make_source', return_value=MagicMock()):
        await s.play_next()
    vc.play.assert_called_once()
    assert guild_state.current_track == sample_track
    assert len(guild_state.queue) == 0



# ---------------------------------------------------------------------------
# skip / stop / pause / resume
# ---------------------------------------------------------------------------

async def test_skip_stops_voice_client(mock_bot, guild_state, sample_track):
    vc = _vc(playing=True)
    guild_state.voice_client = vc
    guild_state.current_track = sample_track
    s = _streamer(mock_bot)
    skipped = await s.skip()
    vc.stop.assert_called_once()
    assert skipped == sample_track


async def test_skip_returns_none_when_not_playing(mock_bot, guild_state):
    guild_state.voice_client = _vc(playing=False)
    s = _streamer(mock_bot)
    assert await s.skip() is None


async def test_stop_clears_queue_and_stops(mock_bot, guild_state, sample_track):
    vc = _vc(playing=True)
    guild_state.voice_client = vc
    guild_state.queue.append(sample_track)
    s = _streamer(mock_bot)
    await s.stop()
    assert len(guild_state.queue) == 0
    vc.stop.assert_called_once()


async def test_pause_calls_vc_pause(mock_bot, guild_state):
    vc = _vc(playing=True)
    guild_state.voice_client = vc
    s = _streamer(mock_bot)
    await s.pause()
    vc.pause.assert_called_once()


async def test_pause_noop_when_not_playing(mock_bot, guild_state):
    vc = _vc(playing=False)
    guild_state.voice_client = vc
    s = _streamer(mock_bot)
    await s.pause()
    vc.pause.assert_not_called()


async def test_pause_accumulates_track_position(mock_bot, guild_state):
    vc = _vc(playing=True)
    guild_state.voice_client = vc
    guild_state.track_play_start = time.monotonic() - 30.0  # pretend 30 s elapsed
    guild_state.track_position_secs = 10.0                  # 10 s already accumulated
    s = _streamer(mock_bot)
    await s.pause()
    assert guild_state.track_position_secs >= 39.9  # ≈ 10 + 30
    assert guild_state.track_play_start is None


async def test_resume_calls_vc_resume(mock_bot, guild_state):
    vc = _vc(paused=True)
    guild_state.voice_client = vc
    s = _streamer(mock_bot)
    await s.resume()
    vc.resume.assert_called_once()


async def test_resume_noop_when_not_paused(mock_bot, guild_state):
    vc = _vc(paused=False)
    guild_state.voice_client = vc
    s = _streamer(mock_bot)
    await s.resume()
    vc.resume.assert_not_called()


async def test_resume_resets_track_play_start(mock_bot, guild_state):
    vc = _vc(paused=True)
    guild_state.voice_client = vc
    guild_state.track_play_start = None
    s = _streamer(mock_bot)
    before = time.monotonic()
    await s.resume()
    assert guild_state.track_play_start is not None
    assert guild_state.track_play_start >= before


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------

async def test_replay_returns_none_when_no_track(mock_bot, guild_state):
    guild_state.voice_client = _vc()
    s = _streamer(mock_bot)
    assert await s.replay() is None


async def test_replay_returns_none_when_no_voice_client(mock_bot, guild_state, sample_track):
    guild_state.current_track = sample_track
    s = _streamer(mock_bot)
    assert await s.replay() is None


async def test_replay_stops_vc_when_playing(mock_bot, guild_state, sample_track):
    vc = _vc(playing=True)
    guild_state.voice_client = vc
    guild_state.current_track = sample_track
    s = _streamer(mock_bot)
    result = await s.replay()
    vc.stop.assert_called_once()
    assert result == sample_track


async def test_replay_stops_vc_when_paused(mock_bot, guild_state, sample_track):
    vc = _vc(paused=True)
    guild_state.voice_client = vc
    guild_state.current_track = sample_track
    s = _streamer(mock_bot)
    result = await s.replay()
    vc.stop.assert_called_once()
    assert result == sample_track


async def test_replay_requeues_track_at_front(mock_bot, guild_state, sample_track):
    other = Track(title='Other', url='u2')
    vc = _vc(playing=True)
    guild_state.voice_client = vc
    guild_state.current_track = sample_track
    guild_state.queue.append(other)
    s = _streamer(mock_bot)
    await s.replay()
    assert guild_state.queue[0] == sample_track
    assert guild_state.queue[1] == other


async def test_replay_resets_seek_to(mock_bot, guild_state, sample_track):
    sample_track.seek_to = 90.0  # had been interrupted mid-track
    vc = _vc(playing=True)
    guild_state.voice_client = vc
    guild_state.current_track = sample_track
    s = _streamer(mock_bot)
    await s.replay()
    assert sample_track.seek_to == 0.0  # must restart from the beginning


async def test_replay_uses_last_track_when_idle(mock_bot, guild_state, sample_track):
    vc = _vc(playing=False, paused=False)
    guild_state.voice_client = vc
    guild_state.last_track = sample_track
    s = _streamer(mock_bot)
    with patch('utils.voice._make_source', return_value=MagicMock()):
        result = await s.replay()
    assert result == sample_track
    vc.play.assert_called_once()


async def test_play_next_sets_last_track(mock_bot, guild_state, sample_track):
    vc = _vc()
    guild_state.voice_client = vc
    guild_state.queue.append(sample_track)
    s = _streamer(mock_bot)
    with patch('utils.voice._make_source', return_value=MagicMock()):
        await s.play_next()
    assert guild_state.last_track == sample_track


# ---------------------------------------------------------------------------
# interrupt
# ---------------------------------------------------------------------------

async def test_play_next_records_timing(mock_bot, guild_state, sample_track):
    vc = _vc()
    guild_state.voice_client = vc
    guild_state.queue.append(sample_track)
    s = _streamer(mock_bot)
    before = time.monotonic()
    with patch('utils.voice._make_source', return_value=MagicMock()):
        await s.play_next()
    assert guild_state.track_play_start is not None
    assert guild_state.track_play_start >= before
    assert guild_state.track_position_secs == 0.0  # fresh track, no seek


async def test_play_next_consumes_seek_to(mock_bot, guild_state, sample_track):
    sample_track.seek_to = 30.0
    vc = _vc()
    guild_state.voice_client = vc
    guild_state.queue.append(sample_track)
    s = _streamer(mock_bot)
    with patch('utils.voice._make_source', return_value=MagicMock()):
        await s.play_next()
    assert sample_track.seek_to == 0.0           # consumed
    assert guild_state.track_position_secs == 30.0  # recorded


async def test_interrupt_stamps_seek_to_on_playing_track(mock_bot, guild_state, sample_track):
    vc = _vc(playing=True)
    guild_state.voice_client = vc
    guild_state.current_track = sample_track
    guild_state.track_play_start = time.monotonic() - 60.0  # 60 s into track
    guild_state.track_position_secs = 0.0
    s = _streamer(mock_bot)
    interrupt_track = Track(title='SFX', url='u')
    with patch('utils.voice._make_source', return_value=MagicMock()):
        await s.interrupt(interrupt_track)
    assert sample_track.seek_to >= 59.9  # ≈ 60 s


async def test_interrupt_stamps_seek_to_on_paused_track(mock_bot, guild_state, sample_track):
    vc = _vc(playing=False, paused=True)
    guild_state.voice_client = vc
    guild_state.current_track = sample_track
    guild_state.track_position_secs = 45.0   # paused after 45 s
    guild_state.track_play_start = None       # cleared when paused
    s = _streamer(mock_bot)
    interrupt_track = Track(title='SFX', url='u')
    with patch('utils.voice._make_source', return_value=MagicMock()):
        await s.interrupt(interrupt_track)
    assert sample_track.seek_to == 45.0


async def test_interrupt_plays_new_source(mock_bot, guild_state, sample_track):
    vc = _vc(playing=True)
    guild_state.voice_client = vc
    guild_state.current_track = sample_track
    s = _streamer(mock_bot)
    interrupt_track = Track(title='SFX', url='u')
    with patch('utils.voice._make_source', return_value=MagicMock()):
        await s.interrupt(interrupt_track)
    vc.stop.assert_called_once()
    vc.play.assert_called_once()


async def test_interrupt_pauses_before_stop(mock_bot, guild_state, sample_track):
    vc = _vc(playing=True)
    guild_state.voice_client = vc
    guild_state.current_track = sample_track
    s = _streamer(mock_bot)
    call_order = []
    vc.pause.side_effect = lambda: call_order.append('pause')
    vc.stop.side_effect = lambda: call_order.append('stop')
    with patch('utils.voice._make_source', return_value=MagicMock()):
        await s.interrupt(Track(title='SFX', url='u'))
    assert call_order == ['pause', 'stop']


async def test_interrupt_noop_when_no_client(mock_bot, guild_state):
    s = _streamer(mock_bot)
    await s.interrupt(Track(title='SFX', url='u'))  # should not raise


# ---------------------------------------------------------------------------
# auto_leave_if_empty
# ---------------------------------------------------------------------------

async def test_auto_leave_when_channel_empty(mock_bot, guild_state):
    vc = _vc()
    guild_state.voice_client = vc
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.members = []  # no members
    await VoiceStreamer.auto_leave_if_empty(mock_bot, 123456789, channel)
    vc.disconnect.assert_awaited_once()


async def test_auto_leave_stays_when_humans_present(mock_bot, guild_state):
    vc = _vc()
    guild_state.voice_client = vc
    human = MagicMock(spec=discord.Member)
    human.bot = False
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.members = [human]
    await VoiceStreamer.auto_leave_if_empty(mock_bot, 123456789, channel)
    vc.disconnect.assert_not_awaited()


# ---------------------------------------------------------------------------
# _make_source
# ---------------------------------------------------------------------------

def test_make_source_uses_file_when_exists(tmp_path, sample_track):
    audio_file = tmp_path / 'test.mp3'
    audio_file.write_bytes(b'')
    sample_track.file_path = audio_file
    with patch('utils.voice.discord.FFmpegPCMAudio') as mock_ffmpeg:
        _make_source(sample_track)
        args = mock_ffmpeg.call_args
        assert str(audio_file) == args.args[0]
        assert args.kwargs.get('before_options') is None  # no seek, no reconnect for local files


def test_make_source_uses_url_when_no_file(sample_track):
    sample_track.file_path = None
    with patch('utils.voice.discord.FFmpegPCMAudio') as mock_ffmpeg:
        _make_source(sample_track)
        args = mock_ffmpeg.call_args
        assert sample_track.url == args.args[0]
        assert 'reconnect' in args.kwargs.get('before_options', '')  # stream reconnect opts


def test_make_source_seek_prepended_for_local_file(tmp_path, sample_track):
    audio_file = tmp_path / 'test.mp3'
    audio_file.write_bytes(b'')
    sample_track.file_path = audio_file
    sample_track.seek_to = 45.5
    with patch('utils.voice.discord.FFmpegPCMAudio') as mock_ffmpeg:
        _make_source(sample_track)
        before = mock_ffmpeg.call_args.kwargs.get('before_options', '')
        assert '-ss 45.500' in before


def test_make_source_seek_prepended_for_stream(sample_track):
    sample_track.file_path = None
    sample_track.seek_to = 120.0
    with patch('utils.voice.discord.FFmpegPCMAudio') as mock_ffmpeg:
        _make_source(sample_track)
        before = mock_ffmpeg.call_args.kwargs.get('before_options', '')
        assert '-ss 120.000' in before
        assert 'reconnect' in before
