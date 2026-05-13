"""Command tests for IntrosCog (cogs/intros.py)."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import discord

from cogs.intros import IntrosCog
from utils.player import get_state


@pytest.fixture
def cog(mock_bot):
    return IntrosCog(mock_bot)


# ---------------------------------------------------------------------------
# !intro set
# ---------------------------------------------------------------------------

class TestIntroSet:
    async def test_invalid_trigger(self, cog, ctx):
        await cog.intro_set.callback(cog, ctx, "invalid")
        ctx.send.assert_called_with("Trigger must be `bot` or `user`.")

    async def test_no_attachment_no_query(self, cog, ctx):
        await cog.intro_set.callback(cog, ctx, "bot", query=None)
        ctx.send.assert_called_with("Provide a URL/search term or attach an MP3 file.")

    async def test_rejects_non_mp3_attachment(self, cog, ctx):
        att = MagicMock()
        att.filename = "file.wav"
        att.read = AsyncMock(return_value=b"data")
        ctx.message.attachments = [att]
        await cog.intro_set.callback(cog, ctx, "bot")
        ctx.send.assert_called_with("Only MP3 attachments are supported.")

    async def test_saves_mp3_attachment(self, cog, ctx, tmp_path):
        att = MagicMock()
        att.filename = "intro.mp3"
        att.read = AsyncMock(return_value=b"\xff\xfb" * 10)
        ctx.message.attachments = [att]

        with patch("cogs.intros.INTRO_SOUNDS_DIR", tmp_path):
            with patch("cogs.intros.load_intro_config", return_value={}):
                with patch("cogs.intros.save_intro_config") as mock_save:
                    await cog.intro_set.callback(cog, ctx, "bot")

        mock_save.assert_called_once()
        saved_data = mock_save.call_args[0][0]
        assert str(ctx.guild.id) in saved_data
        assert "bot" in saved_data[str(ctx.guild.id)]

    async def test_downloads_from_url(self, cog, ctx, sample_track, tmp_path):
        ctx.message.attachments = []
        with patch("cogs.intros.INTRO_SOUNDS_DIR", tmp_path):
            with patch("cogs.intros.download_track", return_value=sample_track):
                with patch("cogs.intros.shutil.copy"):
                    with patch("cogs.intros.load_intro_config", return_value={}):
                        with patch("cogs.intros.save_intro_config") as mock_save:
                            await cog.intro_set.callback(cog, ctx, "user", query="some song")

        mock_save.assert_called_once()

    async def test_download_error_sends_message(self, cog, ctx):
        ctx.message.attachments = []
        with patch("cogs.intros.download_track", side_effect=Exception("fail")):
            await cog.intro_set.callback(cog, ctx, "bot", query="bad url")
        assert any("Could not download" in str(c) for c in ctx.send.call_args_list)


# ---------------------------------------------------------------------------
# !intro clear
# ---------------------------------------------------------------------------

class TestIntroClear:
    async def test_invalid_trigger(self, cog, ctx):
        await cog.intro_clear.callback(cog, ctx, "invalid")
        ctx.send.assert_called_with("Trigger must be `bot` or `user`.")

    async def test_not_configured(self, cog, ctx):
        with patch("cogs.intros.load_intro_config", return_value={}):
            await cog.intro_clear.callback(cog, ctx, "bot")
        ctx.send.assert_called_with("No **bot**-join intro is configured.")

    async def test_clears_existing(self, cog, ctx, tmp_path):
        intro_file = tmp_path / "intro.mp3"
        intro_file.write_bytes(b"fake")
        config = {str(ctx.guild.id): {"bot": {"file": str(intro_file), "source": "x"}}}

        with patch("cogs.intros.load_intro_config", return_value=config):
            with patch("cogs.intros.save_intro_config") as mock_save:
                await cog.intro_clear.callback(cog, ctx, "bot")

        mock_save.assert_called_once()
        assert not intro_file.exists()
        ctx.send.assert_called_with("**Bot-join** intro removed.")


# ---------------------------------------------------------------------------
# !intro show
# ---------------------------------------------------------------------------

class TestIntroShow:
    async def test_show_no_config(self, cog, ctx):
        with patch("cogs.intros.load_intro_config", return_value={}):
            with patch("cogs.intros._INTRO_FILE", Path("/nonexistent/intro.mp3")):
                await cog.intro_show.callback(cog, ctx)
        msg = ctx.send.call_args[0][0]
        assert "Bot join" in msg
        assert "User join" in msg

    async def test_show_with_configured_entry(self, cog, ctx, tmp_path):
        intro = tmp_path / "guild_bot.mp3"
        intro.write_bytes(b"fake")
        config = {str(ctx.guild.id): {"bot": {"file": str(intro), "source": "my_song"}}}

        with patch("cogs.intros.load_intro_config", return_value=config):
            with patch("cogs.intros._INTRO_FILE", Path("/nonexistent.mp3")):
                await cog.intro_show.callback(cog, ctx)

        msg = ctx.send.call_args[0][0]
        assert "guild_bot.mp3" in msg
        assert "my_song" in msg

    async def test_show_flags_missing_file(self, cog, ctx):
        config = {str(ctx.guild.id): {"bot": {"file": "/gone.mp3", "source": "x"}}}
        with patch("cogs.intros.load_intro_config", return_value=config):
            with patch("cogs.intros._INTRO_FILE", Path("/nonexistent.mp3")):
                await cog.intro_show.callback(cog, ctx)
        msg = ctx.send.call_args[0][0]
        assert "missing" in msg


# ---------------------------------------------------------------------------
# on_voice_state_update listener
# ---------------------------------------------------------------------------

class TestVoiceStateUpdate:
    def _make_member(self, is_bot=False, guild_id=111222333):
        m = MagicMock(spec=discord.Member)
        m.bot = is_bot
        m.guild = MagicMock()
        m.guild.id = guild_id
        return m

    def _make_state(self, channel=None):
        s = MagicMock(spec=discord.VoiceState)
        s.channel = channel
        return s

    async def test_ignores_bot_members(self, cog, mock_bot):
        member = self._make_member(is_bot=True)
        await cog.on_voice_state_update(member, self._make_state(), self._make_state(MagicMock()))
        # No state lookup should happen

    async def test_ignores_leave_events(self, cog, mock_bot):
        member = self._make_member()
        before = self._make_state(MagicMock())
        after = self._make_state(None)  # left channel
        with patch("cogs.intros._INTRO_ON_USER_JOIN", True):
            await cog.on_voice_state_update(member, before, after)
        # No play should happen

    async def test_ignores_when_bot_not_in_channel(self, cog, mock_bot):
        member = self._make_member()
        channel = MagicMock()
        before = self._make_state(None)
        after = self._make_state(channel)

        state = get_state(mock_bot, member.guild.id)
        state["voice_client"] = None  # bot not connected

        with patch("cogs.intros._INTRO_ON_USER_JOIN", True):
            with patch("cogs.intros.get_intro_file", return_value=Path("/intro.mp3")):
                await cog.on_voice_state_update(member, before, after)

    async def test_plays_intro_when_bot_idle_in_channel(self, cog, mock_bot, tmp_path):
        member = self._make_member()
        channel = MagicMock()
        before = self._make_state(None)
        after = self._make_state(channel)

        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = False
        vc.is_paused.return_value = False
        vc.channel = channel
        vc.play = MagicMock()

        state = get_state(mock_bot, member.guild.id)
        state["voice_client"] = vc

        intro = tmp_path / "intro.mp3"
        intro.write_bytes(b"fake")

        with patch("cogs.intros._INTRO_ON_USER_JOIN", True):
            with patch("cogs.intros.get_intro_file", return_value=intro):
                with patch("cogs.intros.discord.FFmpegPCMAudio"):
                    await cog.on_voice_state_update(member, before, after)

        vc.play.assert_called_once()

    async def test_does_not_interrupt_playing_music(self, cog, mock_bot, tmp_path):
        member = self._make_member()
        channel = MagicMock()
        before = self._make_state(None)
        after = self._make_state(channel)

        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = True  # already playing
        vc.channel = channel

        state = get_state(mock_bot, member.guild.id)
        state["voice_client"] = vc

        intro = tmp_path / "intro.mp3"
        intro.write_bytes(b"fake")

        with patch("cogs.intros._INTRO_ON_USER_JOIN", True):
            with patch("cogs.intros.get_intro_file", return_value=intro):
                await cog.on_voice_state_update(member, before, after)

        vc.play.assert_not_called()
