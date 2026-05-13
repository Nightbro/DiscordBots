"""Command tests for MusicCog (cogs/music.py)."""
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.music import MusicCog
from utils.player import get_state


@pytest.fixture
def cog(mock_bot):
    return MusicCog(mock_bot)


# ---------------------------------------------------------------------------
# !join / _ensure_voice
# ---------------------------------------------------------------------------

class TestEnsureVoice:
    async def test_rejects_user_not_in_voice(self, cog, ctx_no_voice):
        result = await cog._ensure_voice(ctx_no_voice)
        assert result is False
        ctx_no_voice.send.assert_called_once_with("You need to be in a voice channel.")

    async def test_connects_when_no_vc(self, cog, ctx):
        state = get_state(cog.bot, ctx.guild.id)
        state["voice_client"] = None
        result = await cog._ensure_voice(ctx)
        assert result is True
        assert state["just_connected"] is True

    async def test_sets_just_connected_false_when_already_connected(self, cog, ctx, voice_client):
        voice_client.channel = ctx.author.voice.channel
        state = get_state(cog.bot, ctx.guild.id)
        state["voice_client"] = voice_client
        result = await cog._ensure_voice(ctx)
        assert result is True
        assert state["just_connected"] is False

    async def test_moves_when_in_different_channel(self, cog, ctx, voice_client):
        voice_client.channel = MagicMock()  # different channel
        state = get_state(cog.bot, ctx.guild.id)
        state["voice_client"] = voice_client
        await cog._ensure_voice(ctx)
        voice_client.move_to.assert_called_once_with(ctx.author.voice.channel)


class TestJoin:
    async def test_join_connects(self, cog, ctx):
        state = get_state(cog.bot, ctx.guild.id)
        state["voice_client"] = None
        await cog.join.callback(cog, ctx)
        ctx.send.assert_called_once()
        assert "Joined" in ctx.send.call_args[0][0]

    async def test_join_no_voice_channel(self, cog, ctx_no_voice):
        await cog.join.callback(cog, ctx_no_voice)
        ctx_no_voice.send.assert_called_with("You need to be in a voice channel.")


# ---------------------------------------------------------------------------
# !skip / !pause / !resume
# ---------------------------------------------------------------------------

class TestSkip:
    async def test_skip_while_playing(self, cog, ctx, voice_client):
        voice_client.is_playing.return_value = True
        get_state(cog.bot, ctx.guild.id)["voice_client"] = voice_client
        await cog.skip.callback(cog, ctx)
        voice_client.stop.assert_called_once()
        ctx.send.assert_called_with("Skipped.")

    async def test_skip_when_idle(self, cog, ctx, voice_client):
        voice_client.is_playing.return_value = False
        get_state(cog.bot, ctx.guild.id)["voice_client"] = voice_client
        await cog.skip.callback(cog, ctx)
        ctx.send.assert_called_with("Nothing is playing.")


class TestPause:
    async def test_pause_while_playing(self, cog, ctx, voice_client):
        voice_client.is_playing.return_value = True
        get_state(cog.bot, ctx.guild.id)["voice_client"] = voice_client
        await cog.pause.callback(cog, ctx)
        voice_client.pause.assert_called_once()
        ctx.send.assert_called_with("Paused.")

    async def test_pause_when_idle(self, cog, ctx, voice_client):
        voice_client.is_playing.return_value = False
        get_state(cog.bot, ctx.guild.id)["voice_client"] = voice_client
        await cog.pause.callback(cog, ctx)
        ctx.send.assert_called_with("Nothing is playing.")


class TestResume:
    async def test_resume_while_paused(self, cog, ctx, voice_client):
        voice_client.is_paused.return_value = True
        get_state(cog.bot, ctx.guild.id)["voice_client"] = voice_client
        await cog.resume.callback(cog, ctx)
        voice_client.resume.assert_called_once()
        ctx.send.assert_called_with("Resumed.")

    async def test_resume_when_not_paused(self, cog, ctx, voice_client):
        voice_client.is_paused.return_value = False
        get_state(cog.bot, ctx.guild.id)["voice_client"] = voice_client
        await cog.resume.callback(cog, ctx)
        ctx.send.assert_called_with("Nothing is paused.")


# ---------------------------------------------------------------------------
# !stop
# ---------------------------------------------------------------------------

class TestStop:
    async def test_stop_clears_queue_and_disconnects(self, cog, ctx, voice_client, sample_track):
        state = get_state(cog.bot, ctx.guild.id)
        state["voice_client"] = voice_client
        state["queue"].append(sample_track)
        await cog.stop.callback(cog, ctx)
        assert len(state["queue"]) == 0
        voice_client.stop.assert_called_once()
        voice_client.disconnect.assert_called_once()
        assert state["voice_client"] is None


# ---------------------------------------------------------------------------
# !queue
# ---------------------------------------------------------------------------

class TestShowQueue:
    async def test_empty_queue(self, cog, ctx):
        get_state(cog.bot, ctx.guild.id)["queue"].clear()
        await cog.show_queue.callback(cog, ctx)
        ctx.send.assert_called_with("The queue is empty.")

    async def test_shows_tracks(self, cog, ctx, sample_track):
        state = get_state(cog.bot, ctx.guild.id)
        state["queue"].append(sample_track)
        await cog.show_queue.callback(cog, ctx)
        msg = ctx.send.call_args[0][0]
        assert sample_track["title"] in msg

    async def test_hides_intro_tracks(self, cog, ctx, intro_track, sample_track):
        state = get_state(cog.bot, ctx.guild.id)
        state["queue"].append(intro_track)
        state["queue"].append(sample_track)
        await cog.show_queue.callback(cog, ctx)
        msg = ctx.send.call_args[0][0]
        assert sample_track["title"] in msg
        assert "None" not in msg  # intro title is None


# ---------------------------------------------------------------------------
# !clear / !leave
# ---------------------------------------------------------------------------

class TestClear:
    async def test_clears_queue(self, cog, ctx, sample_track):
        state = get_state(cog.bot, ctx.guild.id)
        state["queue"].append(sample_track)
        await cog.clear.callback(cog, ctx)
        assert len(state["queue"]) == 0
        ctx.send.assert_called_with("Queue cleared.")


class TestLeave:
    async def test_disconnects_when_connected(self, cog, ctx, voice_client):
        state = get_state(cog.bot, ctx.guild.id)
        state["voice_client"] = voice_client
        await cog.leave.callback(cog, ctx)
        voice_client.disconnect.assert_called_once()
        assert state["voice_client"] is None
        ctx.send.assert_called_with("Disconnected.")

    async def test_not_connected(self, cog, ctx, voice_client):
        voice_client.is_connected.return_value = False
        get_state(cog.bot, ctx.guild.id)["voice_client"] = voice_client
        await cog.leave.callback(cog, ctx)
        ctx.send.assert_called_with("Not connected to a voice channel.")


# ---------------------------------------------------------------------------
# !play — queue logic (download is mocked)
# ---------------------------------------------------------------------------

class TestPlay:
    async def test_play_downloads_and_starts(self, cog, ctx, sample_track, voice_client):
        state = get_state(cog.bot, ctx.guild.id)
        state["voice_client"] = voice_client
        state["just_connected"] = False

        with patch("cogs.music.download_track", return_value=sample_track):
            with patch("cogs.music.play_next", new=AsyncMock()) as mock_next:
                await cog.play.callback(cog, ctx, query="test song")

        mock_next.assert_called_once()

    async def test_play_queues_when_already_playing(self, cog, ctx, sample_track, voice_client):
        voice_client.is_playing.return_value = True
        state = get_state(cog.bot, ctx.guild.id)
        state["voice_client"] = voice_client
        state["just_connected"] = False

        with patch("cogs.music.download_track", return_value=sample_track):
            with patch("cogs.music.play_next", new=AsyncMock()) as mock_next:
                await cog.play.callback(cog, ctx, query="test song")

        mock_next.assert_not_called()
        assert any("Added to queue" in str(c) for c in ctx.send.call_args_list)

    async def test_play_handles_download_error(self, cog, ctx, voice_client):
        state = get_state(cog.bot, ctx.guild.id)
        state["voice_client"] = voice_client

        with patch("cogs.music.download_track", side_effect=Exception("network error")):
            await cog.play.callback(cog, ctx, query="broken url")

        assert any("Could not download" in str(c) for c in ctx.send.call_args_list)

    async def test_play_no_voice_channel(self, cog, ctx_no_voice):
        await cog.play.callback(cog, ctx_no_voice, query="test")
        ctx_no_voice.send.assert_called_with("You need to be in a voice channel.")
