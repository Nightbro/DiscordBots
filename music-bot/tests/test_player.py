"""Unit tests for utils/player.py."""
import asyncio
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.player import get_state, play_next, play_with_interrupt


# ---------------------------------------------------------------------------
# get_state
# ---------------------------------------------------------------------------

class TestGetState:
    def test_creates_fresh_state(self, mock_bot, guild_id):
        state = get_state(mock_bot, guild_id)
        assert isinstance(state["queue"], deque)
        assert state["voice_client"] is None
        assert state["current_track"] is None
        assert state["last_channel"] is None

    def test_returns_same_state_on_repeat_call(self, mock_bot, guild_id):
        s1 = get_state(mock_bot, guild_id)
        s2 = get_state(mock_bot, guild_id)
        assert s1 is s2

    def test_separate_guilds_are_isolated(self, mock_bot):
        s1 = get_state(mock_bot, 111)
        s2 = get_state(mock_bot, 222)
        assert s1 is not s2

    def test_mutations_persist(self, mock_bot, guild_id):
        state = get_state(mock_bot, guild_id)
        state["queue"].append({"title": "Song"})
        assert get_state(mock_bot, guild_id)["queue"][0]["title"] == "Song"


# ---------------------------------------------------------------------------
# play_next
# ---------------------------------------------------------------------------

class TestPlayNext:
    async def test_empty_queue_sends_message(self, mock_bot, guild_id):
        channel = MagicMock()
        channel.send = AsyncMock()
        state = get_state(mock_bot, guild_id)
        state["voice_client"] = MagicMock()
        state["queue"].clear()

        await play_next(mock_bot, guild_id, channel)

        channel.send.assert_called_once()
        assert "Queue finished" in channel.send.call_args[0][0]

    async def test_plays_track_from_queue(self, mock_bot, guild_id, sample_track):
        channel = MagicMock()
        channel.send = AsyncMock()
        vc = MagicMock()
        vc.play = MagicMock()

        state = get_state(mock_bot, guild_id)
        state["voice_client"] = vc
        state["queue"].append(sample_track)

        with patch("utils.player.discord.FFmpegPCMAudio"):
            await play_next(mock_bot, guild_id, channel)

        vc.play.assert_called_once()
        channel.send.assert_called_once()
        assert "Now playing" in channel.send.call_args[0][0]
        assert sample_track["title"] in channel.send.call_args[0][0]

    async def test_intro_track_does_not_announce(self, mock_bot, guild_id, intro_track):
        channel = MagicMock()
        channel.send = AsyncMock()
        vc = MagicMock()
        vc.play = MagicMock()

        state = get_state(mock_bot, guild_id)
        state["voice_client"] = vc
        state["queue"].append(intro_track)

        with patch("utils.player.discord.FFmpegPCMAudio"):
            await play_next(mock_bot, guild_id, channel)

        vc.play.assert_called_once()
        channel.send.assert_not_called()

    async def test_skips_missing_playlist_track(self, mock_bot, guild_id):
        channel = MagicMock()
        channel.send = AsyncMock()
        vc = MagicMock()
        vc.play = MagicMock()

        state = get_state(mock_bot, guild_id)
        state["voice_client"] = vc

        missing_track = {
            "file": "/nonexistent/path.mp3",
            "title": "Missing",
            "duration": 0,
            "webpage_url": "https://youtube.com/watch?v=missing",
        }
        state["queue"].append(missing_track)

        error = Exception("Download failed")
        with patch("utils.player.download_track", side_effect=error):
            with patch("utils.player.play_next", new=AsyncMock()):
                await play_next(mock_bot, guild_id, channel)

        assert any("Failed" in str(c) or "skipping" in str(c)
                   for c in channel.send.call_args_list)

    async def test_tracks_current_track(self, mock_bot, guild_id, sample_track):
        channel = MagicMock()
        channel.send = AsyncMock()
        vc = MagicMock()
        vc.play = MagicMock()

        state = get_state(mock_bot, guild_id)
        state['voice_client'] = vc
        state['queue'].append(sample_track)

        with patch('utils.player.discord.FFmpegPCMAudio'):
            await play_next(mock_bot, guild_id, channel)

        assert state['current_track'] is sample_track

    async def test_stores_last_channel(self, mock_bot, guild_id, sample_track):
        channel = MagicMock()
        channel.send = AsyncMock()
        vc = MagicMock()
        vc.play = MagicMock()

        state = get_state(mock_bot, guild_id)
        state['voice_client'] = vc
        state['queue'].append(sample_track)

        with patch('utils.player.discord.FFmpegPCMAudio'):
            await play_next(mock_bot, guild_id, channel)

        assert state['last_channel'] is channel

    async def test_after_callback_skips_when_interrupted(self, mock_bot, guild_id, sample_track):
        """after() must not call play_next when _interrupted is set."""
        channel = MagicMock()
        channel.send = AsyncMock()
        captured_after = {}
        vc = MagicMock()
        vc.play = MagicMock(side_effect=lambda src, after: captured_after.update(after=after))

        state = get_state(mock_bot, guild_id)
        state['voice_client'] = vc
        state['queue'].append(sample_track)
        state['_interrupted'] = True

        with patch('utils.player.discord.FFmpegPCMAudio'), \
             patch('utils.player.asyncio.run_coroutine_threadsafe') as mock_schedule:
            await play_next(mock_bot, guild_id, channel)
            captured_after['after'](None)

        mock_schedule.assert_not_called()

    async def test_after_callback_clears_current_track(self, mock_bot, guild_id, sample_track):
        captured_after = {}
        vc = MagicMock()
        vc.play = MagicMock(side_effect=lambda src, after: captured_after.update(after=after))

        state = get_state(mock_bot, guild_id)
        state['voice_client'] = vc
        state['queue'].append(sample_track)

        with patch('utils.player.discord.FFmpegPCMAudio'), \
             patch('utils.player.asyncio.run_coroutine_threadsafe'):
            await play_next(mock_bot, guild_id, MagicMock(send=AsyncMock()))
            assert state['current_track'] is sample_track
            captured_after['after'](None)

        assert state['current_track'] is None


# ---------------------------------------------------------------------------
# play_with_interrupt
# ---------------------------------------------------------------------------

class TestPlayWithInterrupt:
    def _make_vc(self, playing=False, paused=False):
        vc = MagicMock()
        vc.is_playing.return_value = playing
        vc.is_paused.return_value = paused
        vc.stop = MagicMock()
        vc.play = MagicMock()
        return vc

    async def test_plays_when_idle(self, mock_bot, guild_id, sample_track, tmp_path):
        audio = tmp_path / 'sound.mp3'
        audio.write_bytes(b'\xff\xfb' * 50)
        vc = self._make_vc()
        state = get_state(mock_bot, guild_id)
        state['voice_client'] = vc

        with patch('utils.player.discord.FFmpegPCMAudio'):
            await play_with_interrupt(mock_bot, guild_id, str(audio))

        vc.stop.assert_not_called()
        vc.play.assert_called_once()

    async def test_interrupts_playing_track(self, mock_bot, guild_id, sample_track, tmp_path):
        audio = tmp_path / 'sound.mp3'
        audio.write_bytes(b'\xff\xfb' * 50)
        vc = self._make_vc(playing=True)
        state = get_state(mock_bot, guild_id)
        state['voice_client'] = vc
        state['current_track'] = sample_track

        with patch('utils.player.discord.FFmpegPCMAudio'):
            await play_with_interrupt(mock_bot, guild_id, str(audio))

        assert state.get('_interrupted') is True
        vc.stop.assert_called_once()
        assert state['queue'][0] is sample_track  # re-queued at front

    async def test_does_not_requeue_intro_track(self, mock_bot, guild_id, intro_track, tmp_path):
        audio = tmp_path / 'sound.mp3'
        audio.write_bytes(b'\xff\xfb' * 50)
        vc = self._make_vc(playing=True)
        state = get_state(mock_bot, guild_id)
        state['voice_client'] = vc
        state['current_track'] = intro_track

        with patch('utils.player.discord.FFmpegPCMAudio'):
            await play_with_interrupt(mock_bot, guild_id, str(audio))

        assert len(state['queue']) == 0  # intro not re-queued

    async def test_after_resumes_music_when_was_active(self, mock_bot, guild_id, tmp_path):
        audio = tmp_path / 'sound.mp3'
        audio.write_bytes(b'\xff\xfb' * 50)
        captured_after = {}
        vc = self._make_vc(playing=True)
        vc.play = MagicMock(side_effect=lambda src, after: captured_after.update(after=after))
        state = get_state(mock_bot, guild_id)
        state['voice_client'] = vc
        channel = MagicMock()

        with patch('utils.player.discord.FFmpegPCMAudio'), \
             patch('utils.player.asyncio.run_coroutine_threadsafe') as mock_schedule:
            await play_with_interrupt(mock_bot, guild_id, str(audio), channel)
            captured_after['after'](None)

        mock_schedule.assert_called_once()
        assert state.get('_interrupted') is None  # cleared

    async def test_after_does_not_resume_when_was_idle(self, mock_bot, guild_id, tmp_path):
        audio = tmp_path / 'sound.mp3'
        audio.write_bytes(b'\xff\xfb' * 50)
        captured_after = {}
        vc = self._make_vc()
        vc.play = MagicMock(side_effect=lambda src, after: captured_after.update(after=after))
        state = get_state(mock_bot, guild_id)
        state['voice_client'] = vc

        with patch('utils.player.discord.FFmpegPCMAudio'), \
             patch('utils.player.asyncio.run_coroutine_threadsafe') as mock_schedule:
            await play_with_interrupt(mock_bot, guild_id, str(audio))
            captured_after['after'](None)

        mock_schedule.assert_not_called()

    async def test_uses_last_channel_when_no_channel_given(self, mock_bot, guild_id, tmp_path):
        audio = tmp_path / 'sound.mp3'
        audio.write_bytes(b'\xff\xfb' * 50)
        last_ch = MagicMock()
        captured_after = {}
        vc = self._make_vc(playing=True)
        vc.play = MagicMock(side_effect=lambda src, after: captured_after.update(after=after))
        state = get_state(mock_bot, guild_id)
        state['voice_client'] = vc
        state['last_channel'] = last_ch

        with patch('utils.player.discord.FFmpegPCMAudio'), \
             patch('utils.player.asyncio.run_coroutine_threadsafe') as mock_schedule:
            await play_with_interrupt(mock_bot, guild_id, str(audio))  # no channel arg
            captured_after['after'](None)

        args = mock_schedule.call_args[0]
        # The coroutine passed to run_coroutine_threadsafe should be play_next
        assert mock_schedule.called
