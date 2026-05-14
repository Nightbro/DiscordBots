import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

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


# ---------------------------------------------------------------------------
# interrupt
# ---------------------------------------------------------------------------

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
        assert 'before_options' not in args.kwargs  # file opts, not stream opts


def test_make_source_uses_url_when_no_file(sample_track):
    sample_track.file_path = None
    with patch('utils.voice.discord.FFmpegPCMAudio') as mock_ffmpeg:
        _make_source(sample_track)
        args = mock_ffmpeg.call_args
        assert sample_track.url == args.args[0]
        assert 'before_options' in args.kwargs  # stream reconnect opts
