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


def _make_member(guild, is_bot=False, member_id=999):
    m = MagicMock(spec=discord.Member)
    m.bot = is_bot
    m.guild = guild
    m.id = member_id
    m.display_name = "TestUser"
    m.__str__ = lambda s: "TestUser#0001"
    return m


# ---------------------------------------------------------------------------
# !intro set
# ---------------------------------------------------------------------------

class TestIntroSet:
    async def test_invalid_trigger(self, cog, ctx):
        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(
                side_effect=discord.ext.commands.MemberNotFound("notamember")
            )
            await cog.intro_set.callback(cog, ctx, "notamember")
        ctx.send.assert_called_with(
            "Trigger must be `bot`, `user`, or a @mention of a server member."
        )

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

    async def test_saves_mp3_attachment_for_bot(self, cog, ctx, tmp_path):
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

    async def test_saves_mp3_attachment_for_specific_user(self, cog, ctx, tmp_path):
        member = _make_member(ctx.guild, member_id=42)
        att = MagicMock()
        att.filename = "intro.mp3"
        att.read = AsyncMock(return_value=b"\xff\xfb" * 10)
        ctx.message.attachments = [att]

        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(return_value=member)
            with patch("cogs.intros.INTRO_SOUNDS_DIR", tmp_path):
                with patch("cogs.intros.load_intro_config", return_value={}):
                    with patch("cogs.intros.save_intro_config") as mock_save:
                        await cog.intro_set.callback(cog, ctx, "@TestUser")

        mock_save.assert_called_once()
        saved_data = mock_save.call_args[0][0]
        assert f"user_{member.id}" in saved_data[str(ctx.guild.id)]
        assert saved_data[str(ctx.guild.id)][f"user_{member.id}"]["member_name"] == str(member)

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
        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(
                side_effect=discord.ext.commands.MemberNotFound("notamember")
            )
            await cog.intro_clear.callback(cog, ctx, "notamember")
        ctx.send.assert_called_with(
            "Trigger must be `bot`, `user`, or a @mention of a server member."
        )

    async def test_not_configured(self, cog, ctx):
        with patch("cogs.intros.load_intro_config", return_value={}):
            await cog.intro_clear.callback(cog, ctx, "bot")
        assert any("No intro configured" in str(c) for c in ctx.send.call_args_list)

    async def test_clears_existing_bot(self, cog, ctx, tmp_path):
        intro_file = tmp_path / "intro.mp3"
        intro_file.write_bytes(b"fake")
        config = {str(ctx.guild.id): {"bot": {"file": str(intro_file), "source": "x"}}}

        with patch("cogs.intros.load_intro_config", return_value=config):
            with patch("cogs.intros.save_intro_config") as mock_save:
                await cog.intro_clear.callback(cog, ctx, "bot")

        mock_save.assert_called_once()
        assert not intro_file.exists()
        assert any("Bot-join" in str(c) or "removed" in str(c) for c in ctx.send.call_args_list)

    async def test_clears_per_user_intro(self, cog, ctx, tmp_path):
        member = _make_member(ctx.guild, member_id=42)
        intro_file = tmp_path / "user_42.mp3"
        intro_file.write_bytes(b"fake")
        config = {str(ctx.guild.id): {f"user_{member.id}": {"file": str(intro_file), "source": "x"}}}

        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(return_value=member)
            with patch("cogs.intros.load_intro_config", return_value=config):
                with patch("cogs.intros.save_intro_config") as mock_save:
                    await cog.intro_clear.callback(cog, ctx, "@TestUser")

        mock_save.assert_called_once()
        assert not intro_file.exists()


# ---------------------------------------------------------------------------
# !intro list
# ---------------------------------------------------------------------------

class TestIntroList:
    async def test_no_intros_configured(self, cog, ctx):
        with patch("cogs.intros.load_intro_config", return_value={}):
            await cog.intro_list.callback(cog, ctx)
        ctx.send.assert_called_with("No intros configured for this server yet.")

    async def test_lists_all_triggers(self, cog, ctx, tmp_path):
        bot_file = tmp_path / "bot.mp3"
        bot_file.write_bytes(b"fake")
        user_file = tmp_path / "user.mp3"
        user_file.write_bytes(b"fake")
        config = {
            str(ctx.guild.id): {
                "bot": {"file": str(bot_file), "source": "song1"},
                "user": {"file": str(user_file), "source": "song2"},
                "user_42": {"file": str(user_file), "source": "song3", "member_name": "Alice"},
            }
        }

        with patch("cogs.intros.load_intro_config", return_value=config):
            await cog.intro_list.callback(cog, ctx)

        msg = ctx.send.call_args[0][0]
        assert "bot.mp3" in msg
        assert "user.mp3" in msg
        assert "Alice" in msg
        assert "song1" in msg

    async def test_flags_missing_files(self, cog, ctx):
        config = {
            str(ctx.guild.id): {
                "bot": {"file": "/gone.mp3", "source": "x"},
            }
        }
        with patch("cogs.intros.load_intro_config", return_value=config):
            await cog.intro_list.callback(cog, ctx)
        msg = ctx.send.call_args[0][0]
        assert "missing" in msg


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
        assert "User join" in msg or "Any user" in msg

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

    async def test_show_mentions_per_user_count(self, cog, ctx, tmp_path):
        f = tmp_path / "f.mp3"
        f.write_bytes(b"fake")
        config = {str(ctx.guild.id): {"user_42": {"file": str(f), "source": "x", "member_name": "Bob"}}}
        with patch("cogs.intros.load_intro_config", return_value=config):
            with patch("cogs.intros._INTRO_FILE", Path("/nonexistent.mp3")):
                await cog.intro_show.callback(cog, ctx)
        msg = ctx.send.call_args[0][0]
        assert "1" in msg  # mentions the count


# ---------------------------------------------------------------------------
# on_voice_state_update listener
# ---------------------------------------------------------------------------

class TestVoiceStateUpdate:
    def _make_member(self, mock_bot, is_bot=False, guild_id=111222333, member_id=555):
        m = MagicMock(spec=discord.Member)
        m.bot = is_bot
        m.guild = MagicMock()
        m.guild.id = guild_id
        m.id = member_id
        return m

    def _make_state(self, channel=None):
        s = MagicMock(spec=discord.VoiceState)
        s.channel = channel
        return s

    async def test_ignores_bot_members(self, cog, mock_bot):
        member = self._make_member(mock_bot, is_bot=True)
        await cog.on_voice_state_update(member, self._make_state(), self._make_state(MagicMock()))

    async def test_ignores_leave_events(self, cog, mock_bot):
        member = self._make_member(mock_bot)
        before = self._make_state(MagicMock())
        after = self._make_state(None)
        with patch("cogs.intros._INTRO_ON_USER_JOIN", True):
            await cog.on_voice_state_update(member, before, after)

    async def test_ignores_when_bot_not_in_channel(self, cog, mock_bot):
        member = self._make_member(mock_bot)
        channel = MagicMock()
        before = self._make_state(None)
        after = self._make_state(channel)

        state = get_state(mock_bot, member.guild.id)
        state["voice_client"] = None

        with patch("cogs.intros._INTRO_ON_USER_JOIN", True):
            with patch("cogs.intros.get_user_intro", return_value=Path("/intro.mp3")):
                await cog.on_voice_state_update(member, before, after)

    async def test_plays_intro_when_bot_idle_in_channel(self, cog, mock_bot, tmp_path):
        member = self._make_member(mock_bot)
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
            with patch("cogs.intros.get_user_intro", return_value=intro):
                with patch("cogs.intros.discord.FFmpegPCMAudio"):
                    await cog.on_voice_state_update(member, before, after)

        vc.play.assert_called_once()

    async def test_does_not_interrupt_playing_music(self, cog, mock_bot, tmp_path):
        member = self._make_member(mock_bot)
        channel = MagicMock()
        before = self._make_state(None)
        after = self._make_state(channel)

        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = True
        vc.channel = channel

        state = get_state(mock_bot, member.guild.id)
        state["voice_client"] = vc

        intro = tmp_path / "intro.mp3"
        intro.write_bytes(b"fake")

        with patch("cogs.intros._INTRO_ON_USER_JOIN", True):
            with patch("cogs.intros.get_user_intro", return_value=intro):
                await cog.on_voice_state_update(member, before, after)

        vc.play.assert_not_called()

    async def test_uses_per_user_intro_over_server_wide(self, cog, mock_bot, tmp_path):
        """get_user_intro priority chain is tested here end-to-end via the listener."""
        member = self._make_member(mock_bot, member_id=42)
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

        per_user_intro = tmp_path / "user_42.mp3"
        per_user_intro.write_bytes(b"fake")

        with patch("cogs.intros._INTRO_ON_USER_JOIN", True):
            with patch("cogs.intros.get_user_intro", return_value=per_user_intro) as mock_gui:
                with patch("cogs.intros.discord.FFmpegPCMAudio"):
                    await cog.on_voice_state_update(member, before, after)

        mock_gui.assert_called_once_with(member.guild.id, member.id)
        vc.play.assert_called_once()

    async def test_auto_join_connects_on_first_member(self, cog, mock_bot):
        member = self._make_member(mock_bot)
        channel = MagicMock()
        channel.members = [member]          # only this non-bot member
        channel.connect = AsyncMock(return_value=MagicMock())
        before = self._make_state(None)
        after  = self._make_state(channel)

        state = get_state(mock_bot, member.guild.id)
        state["voice_client"] = None

        with patch("cogs.intros.get_auto_join", return_value=True):
            with patch("cogs.intros._INTRO_ON_USER_JOIN", False):
                await cog.on_voice_state_update(member, before, after)

        channel.connect.assert_called_once()
        assert state["voice_client"] is not None

    async def test_auto_join_does_not_connect_when_already_in_vc(self, cog, mock_bot):
        member = self._make_member(mock_bot)
        channel = MagicMock()
        channel.members = [member]
        channel.connect = AsyncMock()
        before = self._make_state(None)
        after  = self._make_state(channel)

        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = False
        vc.is_paused.return_value = False
        vc.channel = channel
        state = get_state(mock_bot, member.guild.id)
        state["voice_client"] = vc

        with patch("cogs.intros.get_auto_join", return_value=True):
            with patch("cogs.intros._INTRO_ON_USER_JOIN", False):
                await cog.on_voice_state_update(member, before, after)

        channel.connect.assert_not_called()

    async def test_auto_join_does_not_connect_when_not_first_member(self, cog, mock_bot):
        member  = self._make_member(mock_bot)
        other   = MagicMock(spec=discord.Member)
        other.bot = False
        channel = MagicMock()
        channel.members = [member, other]   # already two non-bot members
        channel.connect = AsyncMock()
        before = self._make_state(None)
        after  = self._make_state(channel)

        state = get_state(mock_bot, member.guild.id)
        state["voice_client"] = None

        with patch("cogs.intros.get_auto_join", return_value=True):
            with patch("cogs.intros._INTRO_ON_USER_JOIN", False):
                await cog.on_voice_state_update(member, before, after)

        channel.connect.assert_not_called()

    async def test_auto_join_disabled_does_not_connect(self, cog, mock_bot):
        member = self._make_member(mock_bot)
        channel = MagicMock()
        channel.members = [member]
        channel.connect = AsyncMock()
        before = self._make_state(None)
        after  = self._make_state(channel)

        state = get_state(mock_bot, member.guild.id)
        state["voice_client"] = None

        with patch("cogs.intros.get_auto_join", return_value=False):
            with patch("cogs.intros._INTRO_ON_USER_JOIN", False):
                await cog.on_voice_state_update(member, before, after)

        channel.connect.assert_not_called()


# ---------------------------------------------------------------------------
# !intro autojoin
# ---------------------------------------------------------------------------

class TestIntroAutojoin:
    async def test_enables_autojoin(self, cog, ctx):
        with patch("cogs.intros.set_auto_join") as mock_set:
            await cog.intro_autojoin.callback(cog, ctx, "on")
        mock_set.assert_called_once_with(ctx.guild.id, True)
        assert any("enabled" in str(c) for c in ctx.send.call_args_list)

    async def test_disables_autojoin(self, cog, ctx):
        with patch("cogs.intros.set_auto_join") as mock_set:
            await cog.intro_autojoin.callback(cog, ctx, "off")
        mock_set.assert_called_once_with(ctx.guild.id, False)
        assert any("disabled" in str(c) for c in ctx.send.call_args_list)

    async def test_invalid_state_sends_usage(self, cog, ctx):
        with patch("cogs.intros.set_auto_join") as mock_set:
            await cog.intro_autojoin.callback(cog, ctx, "maybe")
        mock_set.assert_not_called()
        assert any("Usage" in str(c) for c in ctx.send.call_args_list)

    async def test_case_insensitive(self, cog, ctx):
        with patch("cogs.intros.set_auto_join") as mock_set:
            await cog.intro_autojoin.callback(cog, ctx, "ON")
        mock_set.assert_called_once_with(ctx.guild.id, True)
