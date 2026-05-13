"""Unit tests for utils/player.py."""
import asyncio
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.player import get_state, play_next


# ---------------------------------------------------------------------------
# get_state
# ---------------------------------------------------------------------------

class TestGetState:
    def test_creates_fresh_state(self, mock_bot, guild_id):
        state = get_state(mock_bot, guild_id)
        assert isinstance(state["queue"], deque)
        assert state["voice_client"] is None

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
