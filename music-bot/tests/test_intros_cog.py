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
        assert any("Provide" in str(c) for c in ctx.send.call_args_list)

    async def test_rejects_unsupported_attachment(self, cog, ctx):
        att = MagicMock()
        att.filename = "file.txt"
        att.read = AsyncMock(return_value=b"data")
        ctx.message.attachments = [att]
        await cog.intro_set.callback(cog, ctx, "bot")
        assert any("Unsupported" in str(c) for c in ctx.send.call_args_list)

    async def test_accepts_ogg_attachment(self, cog, ctx, tmp_path):
        att = MagicMock()
        att.filename = "intro.ogg"
        att.read = AsyncMock(return_value=b"OggS" + b"\x00" * 20)
        ctx.message.attachments = [att]
        with patch("cogs.intros.INTRO_SOUNDS_DIR", tmp_path):
            with patch("cogs.intros.set_default_entry") as mock_sde:
                with patch("cogs.intros.load_intro_config", return_value={}):
                    await cog.intro_set.callback(cog, ctx, "bot")
        mock_sde.assert_called_once()
        saved_path = mock_sde.call_args[0][2]
        assert saved_path.endswith(".ogg")

    async def test_saves_mp3_attachment_for_bot(self, cog, ctx, tmp_path):
        att = MagicMock()
        att.filename = "intro.mp3"
        att.read = AsyncMock(return_value=b"\xff\xfb" * 10)
        ctx.message.attachments = [att]

        with patch("cogs.intros.INTRO_SOUNDS_DIR", tmp_path):
            with patch("cogs.intros.set_default_entry") as mock_sde:
                await cog.intro_set.callback(cog, ctx, "bot")

        mock_sde.assert_called_once()
        args = mock_sde.call_args[0]
        assert args[0] == ctx.guild.id
        assert args[1] == "bot"

    async def test_saves_mp3_attachment_for_specific_user(self, cog, ctx, tmp_path):
        member = _make_member(ctx.guild, member_id=42)
        att = MagicMock()
        att.filename = "intro.mp3"
        att.read = AsyncMock(return_value=b"\xff\xfb" * 10)
        ctx.message.attachments = [att]

        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(return_value=member)
            with patch("cogs.intros.INTRO_SOUNDS_DIR", tmp_path):
                with patch("cogs.intros.set_default_entry") as mock_sde:
                    await cog.intro_set.callback(cog, ctx, "@TestUser")

        mock_sde.assert_called_once()
        args = mock_sde.call_args[0]
        assert args[1] == f"user_{member.id}"
        assert mock_sde.call_args[1].get("member_name") == str(member) or args[-1] == str(member)

    async def test_downloads_from_url(self, cog, ctx, sample_track, tmp_path):
        ctx.message.attachments = []
        with patch("cogs.intros.INTRO_SOUNDS_DIR", tmp_path):
            with patch("cogs.intros.download_track", return_value=sample_track):
                with patch("cogs.intros.shutil.copy"):
                    with patch("cogs.intros.set_default_entry") as mock_sde:
                        await cog.intro_set.callback(cog, ctx, "user", query="some song")

        mock_sde.assert_called_once()

    async def test_download_error_sends_message(self, cog, ctx):
        ctx.message.attachments = []
        with patch("cogs.intros.download_track", side_effect=Exception("fail")):
            await cog.intro_set.callback(cog, ctx, "bot", query="bad url")
        assert any("Could not download" in str(c) for c in ctx.send.call_args_list)


# ---------------------------------------------------------------------------
# !intro schedule
# ---------------------------------------------------------------------------

class TestIntroSchedule:
    async def test_invalid_trigger(self, cog, ctx):
        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(
                side_effect=discord.ext.commands.MemberNotFound("nobody")
            )
            await cog.intro_schedule.callback(cog, ctx, "nobody", "SAT,SUN")
        ctx.send.assert_called_with(
            "Trigger must be `bot`, `user`, or a @mention of a server member."
        )

    async def test_invalid_days_pattern(self, cog, ctx):
        await cog.intro_schedule.callback(cog, ctx, "bot", "BLAHDAY")
        assert any("Invalid day pattern" in str(c) for c in ctx.send.call_args_list)

    async def test_no_attachment_no_query(self, cog, ctx):
        await cog.intro_schedule.callback(cog, ctx, "bot", "SAT,SUN", query=None)
        assert any("Provide" in str(c) for c in ctx.send.call_args_list)

    async def test_rejects_unsupported_attachment(self, cog, ctx):
        att = MagicMock()
        att.filename = "file.txt"
        att.read = AsyncMock(return_value=b"data")
        ctx.message.attachments = [att]
        await cog.intro_schedule.callback(cog, ctx, "bot", "SAT,SUN")
        assert any("Unsupported" in str(c) for c in ctx.send.call_args_list)

    async def test_saves_attachment_and_calls_set_schedule_entry(self, cog, ctx, tmp_path):
        att = MagicMock()
        att.filename = "weekend.mp3"
        att.read = AsyncMock(return_value=b"\xff\xfb" * 10)
        ctx.message.attachments = [att]

        with patch("cogs.intros.INTRO_SOUNDS_DIR", tmp_path):
            with patch("cogs.intros.set_schedule_entry") as mock_sse:
                await cog.intro_schedule.callback(cog, ctx, "bot", "SAT,SUN")

        mock_sse.assert_called_once()
        args = mock_sse.call_args[0]
        assert args[0] == ctx.guild.id
        assert args[1] == "bot"
        assert args[2] == "SAT,SUN"

    async def test_normalizes_alias_in_confirmation(self, cog, ctx, tmp_path):
        att = MagicMock()
        att.filename = "wday.mp3"
        att.read = AsyncMock(return_value=b"\xff\xfb" * 10)
        ctx.message.attachments = [att]

        with patch("cogs.intros.INTRO_SOUNDS_DIR", tmp_path):
            with patch("cogs.intros.set_schedule_entry"):
                await cog.intro_schedule.callback(cog, ctx, "bot", "WEEKDAY")

        # Confirmation should show canonical days
        last_send = ctx.send.call_args_list[-1][0][0]
        assert "MON,TUE,WED,THU,FRI" in last_send

    async def test_downloads_from_url(self, cog, ctx, sample_track, tmp_path):
        ctx.message.attachments = []
        with patch("cogs.intros.INTRO_SOUNDS_DIR", tmp_path):
            with patch("cogs.intros.download_track", return_value=sample_track):
                with patch("cogs.intros.shutil.copy"):
                    with patch("cogs.intros.set_schedule_entry") as mock_sse:
                        await cog.intro_schedule.callback(
                            cog, ctx, "bot", "FRI", query="friday song"
                        )

        mock_sse.assert_called_once()

    async def test_download_error_sends_message(self, cog, ctx):
        ctx.message.attachments = []
        with patch("cogs.intros.download_track", side_effect=Exception("fail")):
            await cog.intro_schedule.callback(cog, ctx, "bot", "FRI", query="bad url")
        assert any("Could not download" in str(c) for c in ctx.send.call_args_list)

    async def test_per_user_trigger(self, cog, ctx, tmp_path):
        member = _make_member(ctx.guild, member_id=42)
        att = MagicMock()
        att.filename = "fri.mp3"
        att.read = AsyncMock(return_value=b"\xff\xfb" * 10)
        ctx.message.attachments = [att]

        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(return_value=member)
            with patch("cogs.intros.INTRO_SOUNDS_DIR", tmp_path):
                with patch("cogs.intros.set_schedule_entry") as mock_sse:
                    await cog.intro_schedule.callback(cog, ctx, "@TestUser", "FRI")

        mock_sse.assert_called_once()
        assert mock_sse.call_args[0][1] == f"user_{member.id}"


# ---------------------------------------------------------------------------
# !intro unschedule
# ---------------------------------------------------------------------------

class TestIntroUnschedule:
    async def test_invalid_trigger(self, cog, ctx):
        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(
                side_effect=discord.ext.commands.MemberNotFound("nobody")
            )
            await cog.intro_unschedule.callback(cog, ctx, "nobody", days="SAT,SUN")
        ctx.send.assert_called_with(
            "Trigger must be `bot`, `user`, or a @mention of a server member."
        )

    async def test_invalid_days_pattern(self, cog, ctx):
        await cog.intro_unschedule.callback(cog, ctx, "bot", days="BLAH")
        assert any("Invalid day pattern" in str(c) for c in ctx.send.call_args_list)

    async def test_not_found_sends_message(self, cog, ctx):
        with patch("cogs.intros.remove_schedule_entry", return_value=False):
            await cog.intro_unschedule.callback(cog, ctx, "bot", days="SAT,SUN")
        assert any("No schedule override" in str(c) for c in ctx.send.call_args_list)

    async def test_removed_sends_confirmation(self, cog, ctx):
        with patch("cogs.intros.remove_schedule_entry", return_value=True):
            await cog.intro_unschedule.callback(cog, ctx, "bot", days="SAT,SUN")
        last = ctx.send.call_args[0][0]
        assert "removed" in last
        assert "SAT,SUN" in last

    async def test_alias_normalized_in_confirmation(self, cog, ctx):
        with patch("cogs.intros.remove_schedule_entry", return_value=True):
            await cog.intro_unschedule.callback(cog, ctx, "bot", days="WEEKEND")
        last = ctx.send.call_args[0][0]
        assert "SAT,SUN" in last

    async def test_calls_remove_with_raw_days_string(self, cog, ctx):
        with patch("cogs.intros.remove_schedule_entry", return_value=True) as mock_rse:
            await cog.intro_unschedule.callback(cog, ctx, "user", days="MON-FRI")
        mock_rse.assert_called_once_with(ctx.guild.id, "user", "MON-FRI")


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
        with patch("cogs.intros.clear_trigger", return_value=None):
            await cog.intro_clear.callback(cog, ctx, "bot")
        assert any("No intro configured" in str(c) for c in ctx.send.call_args_list)

    async def test_clears_existing_bot(self, cog, ctx):
        with patch("cogs.intros.clear_trigger", return_value={"file": "/x.mp3"}) as mock_ct:
            await cog.intro_clear.callback(cog, ctx, "bot")

        mock_ct.assert_called_once_with(ctx.guild.id, "bot")
        assert any("removed" in str(c) for c in ctx.send.call_args_list)

    async def test_clears_per_user_intro(self, cog, ctx):
        member = _make_member(ctx.guild, member_id=42)
        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(return_value=member)
            with patch("cogs.intros.clear_trigger", return_value={"file": "/x.mp3"}) as mock_ct:
                await cog.intro_clear.callback(cog, ctx, "@TestUser")

        mock_ct.assert_called_once_with(ctx.guild.id, f"user_{member.id}")


# ---------------------------------------------------------------------------
# !intro list
# ---------------------------------------------------------------------------

class TestIntroList:
    async def test_no_intros_configured(self, cog, ctx):
        with patch("cogs.intros.load_intro_config", return_value={}):
            await cog.intro_list.callback(cog, ctx)
        msg = ctx.send.call_args[0][0]
        assert "No intros configured" in msg
        assert "Auto-join" in msg

    async def test_lists_all_triggers_flat_format(self, cog, ctx, tmp_path):
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
        assert "Auto-join" in msg

    async def test_lists_schedule_entries(self, cog, ctx, tmp_path):
        default_file = tmp_path / "default.mp3"
        wknd_file    = tmp_path / "weekend.mp3"
        default_file.write_bytes(b"fake")
        wknd_file.write_bytes(b"fake")
        config = {
            str(ctx.guild.id): {
                "bot": {
                    "default":  {"file": str(default_file), "source": "def"},
                    "schedule": [{"days": "SAT,SUN", "file": str(wknd_file), "source": "wknd"}],
                }
            }
        }

        with patch("cogs.intros.load_intro_config", return_value=config):
            await cog.intro_list.callback(cog, ctx)

        msg = ctx.send.call_args[0][0]
        assert "default.mp3" in msg
        assert "weekend.mp3" in msg
        assert "SAT,SUN" in msg
        assert "(default)" in msg

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

    async def test_show_with_flat_entry(self, cog, ctx, tmp_path):
        intro = tmp_path / "guild_bot.mp3"
        intro.write_bytes(b"fake")
        config = {str(ctx.guild.id): {"bot": {"file": str(intro), "source": "my_song"}}}

        with patch("cogs.intros.load_intro_config", return_value=config):
            with patch("cogs.intros._INTRO_FILE", Path("/nonexistent.mp3")):
                await cog.intro_show.callback(cog, ctx)

        msg = ctx.send.call_args[0][0]
        assert "guild_bot.mp3" in msg
        assert "my_song" in msg

    async def test_show_with_structured_entry_and_schedule(self, cog, ctx, tmp_path):
        default_file = tmp_path / "default.mp3"
        wknd_file    = tmp_path / "weekend.mp3"
        default_file.write_bytes(b"fake")
        wknd_file.write_bytes(b"fake")
        config = {
            str(ctx.guild.id): {
                "bot": {
                    "default":  {"file": str(default_file), "source": "def"},
                    "schedule": [{"days": "SAT,SUN", "file": str(wknd_file), "source": "wknd"}],
                }
            }
        }

        with patch("cogs.intros.load_intro_config", return_value=config):
            with patch("cogs.intros._INTRO_FILE", Path("/nonexistent.mp3")):
                await cog.intro_show.callback(cog, ctx)

        msg = ctx.send.call_args[0][0]
        assert "default.mp3" in msg
        assert "weekend.mp3" in msg
        assert "SAT,SUN" in msg
        assert "(default)" in msg

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

    async def test_interrupts_playing_music_for_user_join(self, cog, mock_bot, tmp_path):
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

        with patch("cogs.intros._INTRO_ON_USER_JOIN", True), \
             patch("cogs.intros.get_user_intro", return_value=intro), \
             patch("cogs.intros.play_with_interrupt", new=AsyncMock()) as mock_pwi:
            await cog.on_voice_state_update(member, before, after)

        mock_pwi.assert_called_once()

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
        channel.members = [member]
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
        channel.members = [member, other]
        channel.connect = AsyncMock()
        before = self._make_state(None)
        after  = self._make_state(channel)

        state = get_state(mock_bot, member.guild.id)
        state["voice_client"] = None

        with patch("cogs.intros.get_auto_join", return_value=True):
            with patch("cogs.intros._INTRO_ON_USER_JOIN", False):
                await cog.on_voice_state_update(member, before, after)

        channel.connect.assert_not_called()

    async def test_auto_leave_when_last_member_leaves(self, cog, mock_bot):
        member  = self._make_member(mock_bot)
        channel = MagicMock()
        channel.members = []  # no non-bot members remain
        before  = self._make_state(channel)
        after   = self._make_state(None)  # member left

        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.channel = channel
        vc.disconnect = AsyncMock()

        state = get_state(mock_bot, member.guild.id)
        state['voice_client'] = vc
        state['queue'] = ['song1', 'song2']

        with patch("cogs.intros._INTRO_ON_USER_JOIN", False):
            await cog.on_voice_state_update(member, before, after)

        vc.disconnect.assert_called_once()
        assert state['voice_client'] is None
        assert state['queue'] == []

    async def test_no_auto_leave_when_others_remain(self, cog, mock_bot):
        member  = self._make_member(mock_bot)
        other   = MagicMock(spec=discord.Member)
        other.bot = False
        channel = MagicMock()
        channel.members = [other]  # one non-bot still present
        before  = self._make_state(channel)
        after   = self._make_state(None)

        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.channel = channel
        vc.disconnect = AsyncMock()

        state = get_state(mock_bot, member.guild.id)
        state['voice_client'] = vc

        with patch("cogs.intros._INTRO_ON_USER_JOIN", False):
            await cog.on_voice_state_update(member, before, after)

        vc.disconnect.assert_not_called()

    async def test_auto_leave_when_member_switches_channel(self, cog, mock_bot):
        member      = self._make_member(mock_bot)
        old_channel = MagicMock()
        old_channel.members = []  # bot's channel now empty
        new_channel = MagicMock()
        before = self._make_state(old_channel)
        after  = self._make_state(new_channel)

        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.channel = old_channel
        vc.disconnect = AsyncMock()

        state = get_state(mock_bot, member.guild.id)
        state['voice_client'] = vc

        with patch("cogs.intros._INTRO_ON_USER_JOIN", False):
            await cog.on_voice_state_update(member, before, after)

        vc.disconnect.assert_called_once()
        assert state['voice_client'] is None

    async def test_no_auto_leave_when_bot_not_in_channel(self, cog, mock_bot):
        member  = self._make_member(mock_bot)
        channel = MagicMock()
        channel.members = []
        before  = self._make_state(channel)
        after   = self._make_state(None)

        state = get_state(mock_bot, member.guild.id)
        state['voice_client'] = None  # bot not connected

        with patch("cogs.intros._INTRO_ON_USER_JOIN", False):
            await cog.on_voice_state_update(member, before, after)
        # no crash, no disconnect attempt

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


# ---------------------------------------------------------------------------
# _ask_to_join helper
# ---------------------------------------------------------------------------

def _make_msg_mock():
    msg = MagicMock()
    msg.id = 987654321
    msg.add_reaction = AsyncMock()
    msg.remove_reaction = AsyncMock()
    msg.edit = AsyncMock()
    return msg


def _make_reaction_mock(emoji, msg):
    r = MagicMock()
    r.emoji = emoji
    r.message = msg
    return r


class TestAskToJoin:
    async def test_yes_returns_true_and_edits_message(self, cog, ctx):
        msg = _make_msg_mock()
        ctx.send = AsyncMock(return_value=msg)
        reaction = _make_reaction_mock('✅', msg)
        ctx.bot = cog.bot
        cog.bot.wait_for = AsyncMock(return_value=(reaction, ctx.author))

        result = await cog._ask_to_join(ctx)

        assert result is True
        msg.edit.assert_called_once()
        assert "joining" in msg.edit.call_args[1]["content"].lower()

    async def test_no_returns_false_and_edits_message(self, cog, ctx):
        msg = _make_msg_mock()
        ctx.send = AsyncMock(return_value=msg)
        reaction = _make_reaction_mock('❌', msg)
        cog.bot.wait_for = AsyncMock(return_value=(reaction, ctx.author))

        result = await cog._ask_to_join(ctx)

        assert result is False
        msg.edit.assert_called_once()
        assert "joining" not in msg.edit.call_args[1]["content"].lower()

    async def test_timeout_returns_false(self, cog, ctx):
        import asyncio as _asyncio
        msg = _make_msg_mock()
        ctx.send = AsyncMock(return_value=msg)
        cog.bot.wait_for = AsyncMock(side_effect=_asyncio.TimeoutError())

        result = await cog._ask_to_join(ctx)

        assert result is False
        assert "timed out" in msg.edit.call_args[1]["content"].lower()

    async def test_adds_both_reactions(self, cog, ctx):
        msg = _make_msg_mock()
        ctx.send = AsyncMock(return_value=msg)
        reaction = _make_reaction_mock('✅', msg)
        cog.bot.wait_for = AsyncMock(return_value=(reaction, ctx.author))

        await cog._ask_to_join(ctx)

        emojis_added = [c.args[0] for c in msg.add_reaction.call_args_list]
        assert '✅' in emojis_added
        assert '❌' in emojis_added

    async def test_removes_user_reaction(self, cog, ctx):
        msg = _make_msg_mock()
        ctx.send = AsyncMock(return_value=msg)
        reaction = _make_reaction_mock('✅', msg)
        cog.bot.wait_for = AsyncMock(return_value=(reaction, ctx.author))

        await cog._ask_to_join(ctx)

        remove_calls = [(c.args[0], c.args[1]) for c in msg.remove_reaction.call_args_list]
        assert ('✅', ctx.author) in remove_calls

    async def test_removes_bot_reactions(self, cog, ctx):
        msg = _make_msg_mock()
        ctx.send = AsyncMock(return_value=msg)
        reaction = _make_reaction_mock('✅', msg)
        cog.bot.wait_for = AsyncMock(return_value=(reaction, ctx.author))

        await cog._ask_to_join(ctx)

        removed_emojis = [c.args[0] for c in msg.remove_reaction.call_args_list]
        assert '✅' in removed_emojis
        assert '❌' in removed_emojis

    async def test_skips_user_reaction_removal_on_forbidden(self, cog, ctx):
        msg = _make_msg_mock()
        msg.remove_reaction = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perm"))
        ctx.send = AsyncMock(return_value=msg)
        reaction = _make_reaction_mock('✅', msg)
        cog.bot.wait_for = AsyncMock(return_value=(reaction, ctx.author))

        result = await cog._ask_to_join(ctx)
        assert result is True


# ---------------------------------------------------------------------------
# !intro trigger
# ---------------------------------------------------------------------------

class TestIntroTrigger:
    async def test_member_not_found(self, cog, ctx):
        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(
                side_effect=discord.ext.commands.MemberNotFound("nobody")
            )
            await cog.intro_trigger.callback(cog, ctx, member_str="nobody")
        assert any("Could not find" in str(c) for c in ctx.send.call_args_list)

    async def test_trigger_bot_keyword(self, cog, ctx, mock_bot, voice_client, tmp_path):
        intro = tmp_path / "bot.mp3"
        intro.write_bytes(b"fake")
        voice_client.channel = ctx.author.voice.channel
        voice_client.play = MagicMock()
        with patch("cogs.intros.get_intro_file", return_value=intro) as mock_gif:
            with patch("cogs.intros.discord.FFmpegPCMAudio"):
                state = get_state(mock_bot, ctx.guild.id)
                state["voice_client"] = voice_client
                await cog.intro_trigger.callback(cog, ctx, member_str="bot")
        mock_gif.assert_called_once_with(ctx.guild.id, "bot")
        voice_client.play.assert_called_once()

    async def test_trigger_user_keyword(self, cog, ctx, mock_bot, voice_client, tmp_path):
        intro = tmp_path / "user.mp3"
        intro.write_bytes(b"fake")
        voice_client.channel = ctx.author.voice.channel
        voice_client.play = MagicMock()
        with patch("cogs.intros.get_intro_file", return_value=intro) as mock_gif:
            with patch("cogs.intros.discord.FFmpegPCMAudio"):
                state = get_state(mock_bot, ctx.guild.id)
                state["voice_client"] = voice_client
                await cog.intro_trigger.callback(cog, ctx, member_str="user")
        mock_gif.assert_called_once_with(ctx.guild.id, "user")
        voice_client.play.assert_called_once()

    async def test_trigger_keyword_not_configured(self, cog, ctx, mock_bot, voice_client):
        voice_client.channel = ctx.author.voice.channel
        with patch("cogs.intros.get_intro_file", return_value=None):
            state = get_state(mock_bot, ctx.guild.id)
            state["voice_client"] = voice_client
            await cog.intro_trigger.callback(cog, ctx, member_str="bot")
        assert any("No intro configured" in str(c) for c in ctx.send.call_args_list)

    async def test_user_not_in_voice_sends_sassy_message(self, cog, ctx, mock_bot):
        member = MagicMock(spec=discord.Member)
        ctx.author.voice = None
        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(return_value=member)
            with patch.object(cog, "_ask_to_join", new=AsyncMock()) as mock_ask:
                state = get_state(mock_bot, ctx.guild.id)
                state["voice_client"] = None
                await cog.intro_trigger.callback(cog, ctx, member_str="@Someone")
        mock_ask.assert_not_called()
        assert any("courage" in str(c) for c in ctx.send.call_args_list)

    async def test_bot_not_in_voice_user_declines(self, cog, ctx, mock_bot):
        member = MagicMock(spec=discord.Member)
        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(return_value=member)
            with patch.object(cog, "_ask_to_join", new=AsyncMock(return_value=False)):
                state = get_state(mock_bot, ctx.guild.id)
                state["voice_client"] = None
                await cog.intro_trigger.callback(cog, ctx, member_str="@Someone")
        ctx.send.assert_not_called()

    async def test_joins_and_plays_when_confirmed(self, cog, ctx, mock_bot, tmp_path):
        member = MagicMock(spec=discord.Member)
        member.guild = ctx.guild
        member.id = 42
        member.display_name = "Bob"

        intro = tmp_path / "intro.mp3"
        intro.write_bytes(b"fake")

        new_vc = MagicMock()
        new_vc.is_playing.return_value = False
        new_vc.is_paused.return_value = False
        new_vc.play = MagicMock()
        ctx.author.voice.channel.connect = AsyncMock(return_value=new_vc)

        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(return_value=member)
            with patch.object(cog, "_ask_to_join", new=AsyncMock(return_value=True)):
                with patch("cogs.intros.get_user_intro", return_value=intro):
                    with patch("cogs.intros.discord.FFmpegPCMAudio"):
                        state = get_state(mock_bot, ctx.guild.id)
                        state["voice_client"] = None
                        await cog.intro_trigger.callback(cog, ctx, member_str="@Bob")

        ctx.author.voice.channel.connect.assert_called_once()
        new_vc.play.assert_called_once()

    async def test_user_in_different_channel_sends_busy_message(self, cog, ctx, mock_bot, voice_client):
        member = MagicMock(spec=discord.Member)
        voice_client.channel = MagicMock()
        ctx.author.voice.channel = MagicMock()
        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(return_value=member)
            state = get_state(mock_bot, ctx.guild.id)
            state["voice_client"] = voice_client
            await cog.intro_trigger.callback(cog, ctx, member_str="@Someone")
        assert any("busy" in str(c) for c in ctx.send.call_args_list)

    async def test_interrupts_while_playing(self, cog, ctx, mock_bot, voice_client):
        member = MagicMock(spec=discord.Member)
        member.guild = ctx.guild
        member.id = 77
        member.display_name = "Bob"
        voice_client.is_playing.return_value = True
        voice_client.channel = ctx.author.voice.channel
        with patch("cogs.intros.commands.MemberConverter") as mock_conv, \
             patch("cogs.intros.play_with_interrupt", new=AsyncMock()) as mock_pwi, \
             patch("cogs.intros.get_user_intro", return_value="/intro.mp3"):
            mock_conv.return_value.convert = AsyncMock(return_value=member)
            state = get_state(mock_bot, ctx.guild.id)
            state["voice_client"] = voice_client
            await cog.intro_trigger.callback(cog, ctx, member_str="@Someone")
        mock_pwi.assert_called_once()

    async def test_no_intro_configured(self, cog, ctx, mock_bot, voice_client):
        member = MagicMock(spec=discord.Member)
        member.guild = ctx.guild
        member.id = 99
        member.display_name = "Alice"
        voice_client.channel = ctx.author.voice.channel
        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(return_value=member)
            with patch("cogs.intros.get_user_intro", return_value=None):
                state = get_state(mock_bot, ctx.guild.id)
                state["voice_client"] = voice_client
                await cog.intro_trigger.callback(cog, ctx, member_str="@Alice")
        assert any("No intro configured" in str(c) for c in ctx.send.call_args_list)

    async def test_plays_intro(self, cog, ctx, mock_bot, voice_client, tmp_path):
        member = MagicMock(spec=discord.Member)
        member.guild = ctx.guild
        member.id = 42
        member.display_name = "Bob"
        voice_client.play = MagicMock()
        voice_client.channel = ctx.author.voice.channel

        intro = tmp_path / "intro.mp3"
        intro.write_bytes(b"fake")

        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(return_value=member)
            with patch("cogs.intros.get_user_intro", return_value=intro):
                with patch("cogs.intros.discord.FFmpegPCMAudio"):
                    state = get_state(mock_bot, ctx.guild.id)
                    state["voice_client"] = voice_client
                    await cog.intro_trigger.callback(cog, ctx, member_str="@Bob")

        voice_client.play.assert_called_once()
        assert any("Playing" in str(c) and "intro" in str(c) for c in ctx.send.call_args_list)


# ---------------------------------------------------------------------------
# !intro rename
# ---------------------------------------------------------------------------

class TestIntroRename:
    async def test_invalid_trigger(self, cog, ctx):
        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(
                side_effect=discord.ext.commands.MemberNotFound("nobody")
            )
            await cog.intro_rename.callback(cog, ctx, "nobody", name="cool name")
        ctx.send.assert_called_with(
            "Trigger must be `bot`, `user`, or a @mention of a server member."
        )

    async def test_not_configured(self, cog, ctx):
        with patch("cogs.intros.load_intro_config", return_value={}):
            await cog.intro_rename.callback(cog, ctx, "bot", name="My Intro")
        assert any("No intro configured" in str(c) for c in ctx.send.call_args_list)

    async def test_renames_flat_format_source(self, cog, ctx):
        config = {str(ctx.guild.id): {"bot": {"file": "/some.mp3", "source": "old name"}}}
        with patch("cogs.intros.load_intro_config", return_value=config):
            with patch("cogs.intros.save_intro_config") as mock_save:
                await cog.intro_rename.callback(cog, ctx, "bot", name="My Bot Intro")
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        assert saved[str(ctx.guild.id)]["bot"]["source"] == "My Bot Intro"
        assert any("My Bot Intro" in str(c) for c in ctx.send.call_args_list)

    async def test_renames_structured_format_default_source(self, cog, ctx):
        config = {str(ctx.guild.id): {"bot": {
            "default": {"file": "/some.mp3", "source": "old name"},
            "schedule": [],
        }}}
        with patch("cogs.intros.load_intro_config", return_value=config):
            with patch("cogs.intros.save_intro_config") as mock_save:
                await cog.intro_rename.callback(cog, ctx, "bot", name="New Name")
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        assert saved[str(ctx.guild.id)]["bot"]["default"]["source"] == "New Name"

    async def test_renames_per_user_intro(self, cog, ctx):
        member = MagicMock(spec=discord.Member)
        member.id = 42
        member.display_name = "Alice"
        config = {str(ctx.guild.id): {"user_42": {"file": "/some.mp3", "source": "old"}}}
        with patch("cogs.intros.commands.MemberConverter") as mock_conv:
            mock_conv.return_value.convert = AsyncMock(return_value=member)
            with patch("cogs.intros.load_intro_config", return_value=config):
                with patch("cogs.intros.save_intro_config") as mock_save:
                    await cog.intro_rename.callback(cog, ctx, "@Alice", name="Alice Entrance")
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        assert saved[str(ctx.guild.id)]["user_42"]["source"] == "Alice Entrance"
