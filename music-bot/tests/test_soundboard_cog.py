"""Tests for cogs/soundboard.py"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import utils.soundboard_config as sbc
from cogs.soundboard import SoundboardCog
from utils.player import get_state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_soundboard_config(tmp_path, monkeypatch):
    cfg_file = tmp_path / 'soundboard_config.json'
    monkeypatch.setattr(sbc, 'SOUNDBOARD_CONFIG_FILE', cfg_file)


@pytest.fixture
def cog(mock_bot):
    return SoundboardCog(mock_bot)


@pytest.fixture
def sound_file(tmp_path):
    f = tmp_path / 'boom.mp3'
    f.write_bytes(b'\xff\xfb' * 50)
    return f


@pytest.fixture
def ctx_with_vc(ctx, voice_client, mock_bot):
    state = get_state(mock_bot, ctx.guild.id)
    state['voice_client'] = voice_client
    voice_client.channel = ctx.author.voice.channel
    return ctx


def _panel_msg(guild_id):
    """A mock message suitable for use as a soundboard panel."""
    msg = AsyncMock()
    msg.id = 9999
    msg.add_reaction = AsyncMock()
    msg.remove_reaction = AsyncMock()
    return msg


def _make_payload(guild_id, msg_id, emoji_str, member, channel_id=1):
    payload = MagicMock()
    payload.guild_id   = guild_id
    payload.message_id = msg_id
    payload.channel_id = channel_id
    payload.member     = member
    payload.user_id    = member.id
    emoji = MagicMock()
    emoji.__str__ = MagicMock(return_value=emoji_str)
    payload.emoji = emoji
    return payload


# ---------------------------------------------------------------------------
# TestSendPanel
# ---------------------------------------------------------------------------

class TestSendPanel:
    async def test_empty_panel(self, cog, ctx):
        await cog._send_panel(ctx)
        assert 'No sounds' in ctx.send.call_args[0][0]

    async def test_panel_lists_sounds(self, cog, ctx, sound_file):
        sbc.add_sound(ctx.guild.id, 'boom', '💥', str(sound_file), 'test src')
        msg = _panel_msg(ctx.guild.id)
        ctx.send = AsyncMock(return_value=msg)

        await cog._send_panel(ctx)

        text = ctx.send.call_args[0][0]
        assert 'boom' in text
        assert '💥' in text
        assert 'test src' in text

    async def test_panel_adds_reactions(self, cog, ctx, sound_file):
        sbc.add_sound(ctx.guild.id, 'boom', '💥', str(sound_file), 'src')
        sbc.add_sound(ctx.guild.id, 'ping', '🔔', str(sound_file), 'src2')
        msg = _panel_msg(ctx.guild.id)
        ctx.send = AsyncMock(return_value=msg)

        await cog._send_panel(ctx)

        added = [str(c.args[0]) for c in msg.add_reaction.call_args_list]
        assert '💥' in added
        assert '🔔' in added

    async def test_panel_stored(self, cog, ctx, sound_file):
        sbc.add_sound(ctx.guild.id, 'boom', '💥', str(sound_file), 'src')
        msg = _panel_msg(ctx.guild.id)
        ctx.send = AsyncMock(return_value=msg)

        with patch.object(cog, '_reset_panel_timer'):
            await cog._send_panel(ctx)

        assert ctx.guild.id in cog._panels
        stored_msg, emoji_map = cog._panels[ctx.guild.id]
        assert stored_msg is msg
        assert emoji_map['💥'] == 'boom'

    async def test_panel_starts_timer(self, cog, ctx, sound_file):
        sbc.add_sound(ctx.guild.id, 'boom', '💥', str(sound_file), 'src')
        msg = _panel_msg(ctx.guild.id)
        ctx.send = AsyncMock(return_value=msg)

        with patch.object(cog, '_reset_panel_timer') as mock_reset:
            await cog._send_panel(ctx)

        mock_reset.assert_called_once_with(ctx.guild.id)

    async def test_sb_group_calls_panel(self, cog, ctx):
        with patch.object(cog, '_send_panel', new=AsyncMock()) as mock_panel:
            await cog.sb_group.callback(cog, ctx)
        mock_panel.assert_called_once_with(ctx)

    async def test_sb_list_calls_panel(self, cog, ctx):
        with patch.object(cog, '_send_panel', new=AsyncMock()) as mock_panel:
            await cog.sb_list.callback(cog, ctx)
        mock_panel.assert_called_once_with(ctx)


# ---------------------------------------------------------------------------
# TestSbAdd
# ---------------------------------------------------------------------------

class TestSbAdd:
    async def test_add_no_attachment_no_query(self, cog, ctx):
        await cog.sb_add.callback(cog, ctx, 'boom', '💥', query=None)
        assert 'Provide' in ctx.send.call_args[0][0]

    async def test_add_non_mp3_attachment(self, cog, ctx):
        attachment = MagicMock()
        attachment.filename = 'file.wav'
        ctx.message.attachments = [attachment]
        await cog.sb_add.callback(cog, ctx, 'boom', '💥', query=None)
        assert 'MP3' in ctx.send.call_args[0][0]

    async def test_add_from_attachment(self, cog, ctx, tmp_path):
        dest_dir = tmp_path / 'soundboard'
        dest_dir.mkdir()
        attachment = MagicMock()
        attachment.filename = 'boom.mp3'
        attachment.read = AsyncMock(return_value=b'\xff\xfb' * 50)
        ctx.message.attachments = [attachment]

        with patch('cogs.soundboard.SOUNDBOARD_DIR', dest_dir):
            await cog.sb_add.callback(cog, ctx, 'boom', '💥', query=None)

        calls = [str(c) for c in ctx.send.call_args_list]
        assert any('boom' in c and 'added' in c for c in calls)
        assert sbc.get_sound(ctx.guild.id, 'boom') is not None

    async def test_add_from_url(self, cog, ctx, sound_file, tmp_path):
        dest_dir = tmp_path / 'soundboard'
        dest_dir.mkdir()
        fake_track = {'file': str(sound_file), 'title': 'Boom', 'duration': 5}

        with patch('cogs.soundboard.SOUNDBOARD_DIR', dest_dir), \
             patch('cogs.soundboard.download_track', return_value=fake_track):
            await cog.sb_add.callback(cog, ctx, 'boom', '💥', query='boom sound')

        calls = [str(c) for c in ctx.send.call_args_list]
        assert any('boom' in c and 'added' in c for c in calls)
        assert sbc.get_sound(ctx.guild.id, 'boom') is not None

    async def test_add_download_failure(self, cog, ctx):
        with patch('cogs.soundboard.download_track', side_effect=Exception('network error')):
            await cog.sb_add.callback(cog, ctx, 'boom', '💥', query='bad url')
        assert 'Could not download' in ctx.send.call_args[0][0]


# ---------------------------------------------------------------------------
# TestSbRemove
# ---------------------------------------------------------------------------

class TestSbRemove:
    async def test_remove_not_found(self, cog, ctx):
        await cog.sb_remove.callback(cog, ctx, name='ghost')
        assert 'No sound' in ctx.send.call_args[0][0]

    async def test_remove_existing(self, cog, ctx, sound_file):
        sbc.add_sound(ctx.guild.id, 'boom', '💥', str(sound_file), 'src')
        await cog.sb_remove.callback(cog, ctx, name='boom')
        assert 'removed' in ctx.send.call_args[0][0]
        assert sbc.get_sound(ctx.guild.id, 'boom') is None

    async def test_remove_deletes_file(self, cog, ctx, sound_file):
        sbc.add_sound(ctx.guild.id, 'boom', '💥', str(sound_file), 'src')
        assert sound_file.exists()
        await cog.sb_remove.callback(cog, ctx, name='boom')
        assert not sound_file.exists()


# ---------------------------------------------------------------------------
# TestSbTrigger (command)
# ---------------------------------------------------------------------------

class TestSbTrigger:
    async def test_sound_not_found(self, cog, ctx):
        await cog.sb_trigger.callback(cog, ctx, name='ghost')
        assert 'No sound' in ctx.send.call_args[0][0]

    async def test_user_not_in_voice(self, cog, ctx_no_voice, sound_file):
        sbc.add_sound(ctx_no_voice.guild.id, 'boom', '💥', str(sound_file), 'src')
        await cog.sb_trigger.callback(cog, ctx_no_voice, name='boom')
        assert 'courage' in ctx_no_voice.send.call_args[0][0]

    async def test_bot_busy_different_channel(self, cog, ctx, voice_client, mock_bot, sound_file):
        sbc.add_sound(ctx.guild.id, 'boom', '💥', str(sound_file), 'src')
        state = get_state(mock_bot, ctx.guild.id)
        state['voice_client'] = voice_client
        voice_client.channel = MagicMock()  # different channel
        await cog.sb_trigger.callback(cog, ctx, name='boom')
        assert 'busy' in ctx.send.call_args[0][0]

    async def test_interrupts_while_playing(self, cog, ctx_with_vc, voice_client, sound_file):
        sbc.add_sound(ctx_with_vc.guild.id, 'boom', '💥', str(sound_file), 'src')
        voice_client.is_playing.return_value = True
        with patch('cogs.soundboard.play_with_interrupt', new=AsyncMock()) as mock_pwi:
            await cog.sb_trigger.callback(cog, ctx_with_vc, name='boom')
        mock_pwi.assert_called_once()

    async def test_interrupts_while_paused(self, cog, ctx_with_vc, voice_client, sound_file):
        sbc.add_sound(ctx_with_vc.guild.id, 'boom', '💥', str(sound_file), 'src')
        voice_client.is_paused.return_value = True
        with patch('cogs.soundboard.play_with_interrupt', new=AsyncMock()) as mock_pwi:
            await cog.sb_trigger.callback(cog, ctx_with_vc, name='boom')
        mock_pwi.assert_called_once()

    async def test_missing_file(self, cog, ctx_with_vc, tmp_path, sound_file):
        sbc.add_sound(ctx_with_vc.guild.id, 'boom', '💥', str(tmp_path / 'missing.mp3'), 'src')
        await cog.sb_trigger.callback(cog, ctx_with_vc, name='boom')
        assert 'missing' in ctx_with_vc.send.call_args[0][0]

    async def test_plays_sound(self, cog, ctx_with_vc, voice_client, sound_file):
        sbc.add_sound(ctx_with_vc.guild.id, 'boom', '💥', str(sound_file), 'src')
        with patch('cogs.soundboard.play_with_interrupt', new=AsyncMock()) as mock_pwi:
            await cog.sb_trigger.callback(cog, ctx_with_vc, name='boom')
        mock_pwi.assert_called_once()
        calls = [str(c) for c in ctx_with_vc.send.call_args_list]
        assert any('Playing' in c and 'boom' in c for c in calls)

    async def test_bot_not_in_voice_confirm_yes(self, cog, ctx, sound_file, mock_bot):
        sbc.add_sound(ctx.guild.id, 'boom', '💥', str(sound_file), 'src')
        new_vc = MagicMock()
        new_vc.is_connected.return_value = True
        new_vc.is_playing.return_value = False
        new_vc.is_paused.return_value = False
        new_vc.play = MagicMock()
        ctx.author.voice.channel.connect = AsyncMock(return_value=new_vc)

        with patch.object(cog, '_ask_to_join', new=AsyncMock(return_value=True)), \
             patch('cogs.soundboard.play_with_interrupt', new=AsyncMock()):
            await cog.sb_trigger.callback(cog, ctx, name='boom')

        assert get_state(mock_bot, ctx.guild.id)['voice_client'] is new_vc

    async def test_bot_not_in_voice_confirm_no(self, cog, ctx, sound_file, mock_bot):
        sbc.add_sound(ctx.guild.id, 'boom', '💥', str(sound_file), 'src')
        with patch.object(cog, '_ask_to_join', new=AsyncMock(return_value=False)):
            await cog.sb_trigger.callback(cog, ctx, name='boom')
        assert get_state(mock_bot, ctx.guild.id)['voice_client'] is None


# ---------------------------------------------------------------------------
# TestPlayFromReaction
# ---------------------------------------------------------------------------

class TestPlayFromReaction:
    def _make_guild(self, guild_id, voice_client=None):
        guild = MagicMock()
        guild.id = guild_id
        return guild

    async def test_sound_not_found_is_silent(self, cog, mock_bot):
        guild = self._make_guild(1)
        channel = AsyncMock()
        member = MagicMock()
        member.voice = MagicMock()
        await cog._play_from_reaction(guild, channel, member, 'ghost')
        channel.send.assert_not_called()

    async def test_user_not_in_voice(self, cog, mock_bot, sound_file):
        guild = self._make_guild(mock_bot.guild_states and 1 or 1)
        guild.id = 111222333
        sbc.add_sound(guild.id, 'boom', '💥', str(sound_file), 'src')
        channel = AsyncMock()
        member = MagicMock()
        member.voice = None
        await cog._play_from_reaction(guild, channel, member, 'boom')
        channel.send.assert_called_once()
        assert 'courage' in channel.send.call_args[0][0]

    async def test_bot_busy_different_channel(self, cog, mock_bot, voice_client, sound_file):
        guild = MagicMock()
        guild.id = 111222333
        sbc.add_sound(guild.id, 'boom', '💥', str(sound_file), 'src')
        state = get_state(mock_bot, guild.id)
        state['voice_client'] = voice_client
        voice_client.channel = MagicMock()  # different from member's channel

        channel = AsyncMock()
        member = MagicMock()
        member.voice = MagicMock()
        member.voice.channel = MagicMock()  # different object

        await cog._play_from_reaction(guild, channel, member, 'boom')
        assert 'busy' in channel.send.call_args[0][0]

    async def test_auto_joins_if_bot_not_in_voice(self, cog, mock_bot, sound_file):
        guild = MagicMock()
        guild.id = 111222333
        sbc.add_sound(guild.id, 'boom', '💥', str(sound_file), 'src')

        new_vc = MagicMock()
        new_vc.is_connected.return_value = True
        new_vc.is_playing.return_value = False
        new_vc.is_paused.return_value = False
        new_vc.play = MagicMock()

        channel = AsyncMock()
        member = MagicMock()
        member.voice = MagicMock()
        member.voice.channel.connect = AsyncMock(return_value=new_vc)

        with patch('cogs.soundboard.play_with_interrupt', new=AsyncMock()):
            await cog._play_from_reaction(guild, channel, member, 'boom')

        assert get_state(mock_bot, guild.id)['voice_client'] is new_vc

    async def test_interrupts_while_playing(self, cog, mock_bot, voice_client, sound_file):
        guild = MagicMock()
        guild.id = 111222333
        sbc.add_sound(guild.id, 'boom', '💥', str(sound_file), 'src')
        state = get_state(mock_bot, guild.id)
        state['voice_client'] = voice_client
        voice_client.is_playing.return_value = True

        channel = AsyncMock()
        member = MagicMock()
        member.voice = MagicMock()
        member.voice.channel = voice_client.channel

        with patch('cogs.soundboard.play_with_interrupt', new=AsyncMock()) as mock_pwi:
            await cog._play_from_reaction(guild, channel, member, 'boom')
        mock_pwi.assert_called_once()

    async def test_missing_file(self, cog, mock_bot, voice_client, tmp_path):
        guild = MagicMock()
        guild.id = 111222333
        sbc.add_sound(guild.id, 'boom', '💥', str(tmp_path / 'missing.mp3'), 'src')
        state = get_state(mock_bot, guild.id)
        state['voice_client'] = voice_client

        channel = AsyncMock()
        member = MagicMock()
        member.voice = MagicMock()
        member.voice.channel = voice_client.channel

        await cog._play_from_reaction(guild, channel, member, 'boom')
        assert 'missing' in channel.send.call_args[0][0]

    async def test_plays_and_mentions_member(self, cog, mock_bot, voice_client, sound_file):
        guild = MagicMock()
        guild.id = 111222333
        sbc.add_sound(guild.id, 'boom', '💥', str(sound_file), 'src')
        state = get_state(mock_bot, guild.id)
        state['voice_client'] = voice_client

        channel = AsyncMock()
        member = MagicMock()
        member.mention = '<@42>'
        member.voice = MagicMock()
        member.voice.channel = voice_client.channel

        with patch('cogs.soundboard.play_with_interrupt', new=AsyncMock()):
            await cog._play_from_reaction(guild, channel, member, 'boom')

        msg = channel.send.call_args[0][0]
        assert 'Playing' in msg and 'boom' in msg and '<@42>' in msg


# ---------------------------------------------------------------------------
# TestOnRawReactionAdd
# ---------------------------------------------------------------------------

class TestOnRawReactionAdd:
    def _register_panel(self, cog, guild_id, msg_id, emoji_map):
        panel_msg = AsyncMock()
        panel_msg.id = msg_id
        panel_msg.remove_reaction = AsyncMock()
        cog._panels[guild_id] = (panel_msg, emoji_map)
        return panel_msg

    async def test_ignores_bot_own_reaction(self, cog, mock_bot, sound_file):
        mock_bot.user = MagicMock()
        mock_bot.user.id = 99
        self._register_panel(cog, 1, 9999, {'💥': 'boom'})
        payload = MagicMock()
        payload.user_id = 99  # bot itself
        payload.guild_id = 1
        await cog.on_raw_reaction_add(payload)
        # No guild lookup or sound play should happen

    async def test_ignores_unknown_guild(self, cog, mock_bot, sound_file):
        mock_bot.user = MagicMock(id=99)
        payload = MagicMock()
        payload.user_id = 1
        payload.guild_id = 777  # no panel for this guild
        await cog.on_raw_reaction_add(payload)

    async def test_ignores_wrong_message(self, cog, mock_bot):
        mock_bot.user = MagicMock(id=99)
        self._register_panel(cog, 1, 9999, {'💥': 'boom'})
        payload = MagicMock()
        payload.user_id = 1
        payload.guild_id = 1
        payload.message_id = 1111  # wrong message
        await cog.on_raw_reaction_add(payload)

    async def test_ignores_unknown_emoji(self, cog, mock_bot, sound_file):
        mock_bot.user = MagicMock(id=99)
        self._register_panel(cog, 1, 9999, {'💥': 'boom'})

        member = MagicMock()
        member.id = 42
        guild = MagicMock()
        guild.id = 1
        channel = AsyncMock()
        guild.get_channel = MagicMock(return_value=channel)
        mock_bot.get_guild = MagicMock(return_value=guild)

        payload = _make_payload(1, 9999, '🎵', member, channel_id=5)
        payload.user_id = 42
        await cog.on_raw_reaction_add(payload)

    async def test_reaction_removes_and_plays(self, cog, mock_bot, sound_file, voice_client):
        mock_bot.user = MagicMock(id=99)
        guild_id = 111222333
        sbc.add_sound(guild_id, 'boom', '💥', str(sound_file), 'src')
        panel_msg = self._register_panel(cog, guild_id, 9999, {'💥': 'boom'})

        state = get_state(mock_bot, guild_id)
        state['voice_client'] = voice_client

        channel = AsyncMock()
        member = MagicMock()
        member.id = 42
        member.mention = '<@42>'
        member.voice = MagicMock()
        member.voice.channel = voice_client.channel

        guild = MagicMock()
        guild.id = guild_id
        guild.get_channel = MagicMock(return_value=channel)
        mock_bot.get_guild = MagicMock(return_value=guild)

        payload = _make_payload(guild_id, 9999, '💥', member, channel_id=5)
        payload.user_id = 42

        with patch.object(cog, '_reset_panel_timer'), \
             patch('cogs.soundboard.play_with_interrupt', new=AsyncMock()):
            await cog.on_raw_reaction_add(payload)

        panel_msg.remove_reaction.assert_called_once()

    async def test_reaction_resets_timer(self, cog, mock_bot, sound_file, voice_client):
        mock_bot.user = MagicMock(id=99)
        guild_id = 111222333
        sbc.add_sound(guild_id, 'boom', '💥', str(sound_file), 'src')
        self._register_panel(cog, guild_id, 9999, {'💥': 'boom'})

        state = get_state(mock_bot, guild_id)
        state['voice_client'] = voice_client

        channel = AsyncMock()
        member = MagicMock()
        member.id = 42
        member.voice = MagicMock()
        member.voice.channel = voice_client.channel

        guild = MagicMock()
        guild.id = guild_id
        guild.get_channel = MagicMock(return_value=channel)
        mock_bot.get_guild = MagicMock(return_value=guild)

        payload = _make_payload(guild_id, 9999, '💥', member, channel_id=5)
        payload.user_id = 42

        with patch.object(cog, '_reset_panel_timer') as mock_reset, \
             patch('cogs.soundboard.play_with_interrupt', new=AsyncMock()):
            await cog.on_raw_reaction_add(payload)

        mock_reset.assert_called_once_with(guild_id)

    async def test_reaction_no_guild_in_cache(self, cog, mock_bot):
        mock_bot.user = MagicMock(id=99)
        self._register_panel(cog, 1, 9999, {'💥': 'boom'})
        mock_bot.get_guild = MagicMock(return_value=None)

        payload = _make_payload(1, 9999, '💥', MagicMock(id=42), channel_id=5)
        payload.user_id = 42
        # Should not raise
        await cog.on_raw_reaction_add(payload)


# ---------------------------------------------------------------------------
# TestPanelTimeout
# ---------------------------------------------------------------------------

class TestPanelTimeout:
    async def test_timeout_edits_message(self, cog):
        panel_msg = AsyncMock()
        panel_msg.clear_reactions = AsyncMock()
        panel_msg.edit = AsyncMock()
        cog._panels[1] = (panel_msg, {'💥': 'boom'})

        with patch('cogs.soundboard.asyncio.sleep', new=AsyncMock()):
            await cog._panel_timeout(1)

        panel_msg.clear_reactions.assert_called_once()
        panel_msg.edit.assert_called_once()
        assert '!sb' in panel_msg.edit.call_args[1].get('content', '') or \
               '!sb' in str(panel_msg.edit.call_args)
        assert 1 not in cog._panels

    async def test_timeout_clears_task_entry(self, cog):
        panel_msg = AsyncMock()
        cog._panels[1] = (panel_msg, {})
        cog._panel_tasks[1] = MagicMock()

        with patch('cogs.soundboard.asyncio.sleep', new=AsyncMock()):
            await cog._panel_timeout(1)

        assert 1 not in cog._panel_tasks

    async def test_timeout_silent_on_http_error(self, cog):
        panel_msg = AsyncMock()
        panel_msg.clear_reactions = AsyncMock(side_effect=discord.HTTPException(MagicMock(), 'gone'))
        panel_msg.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), 'gone'))
        cog._panels[1] = (panel_msg, {})

        with patch('cogs.soundboard.asyncio.sleep', new=AsyncMock()):
            await cog._panel_timeout(1)  # should not raise

    async def test_timeout_noop_when_panel_already_gone(self, cog):
        # Panel may have been replaced by a new one before timeout fires
        with patch('cogs.soundboard.asyncio.sleep', new=AsyncMock()):
            await cog._panel_timeout(999)  # unknown guild — should not raise

    async def test_reset_timer_cancels_old_task(self, cog):
        old_task = MagicMock()
        cog._panel_tasks[1] = old_task
        captured = []

        def capture(coro):
            captured.append(coro)
            return MagicMock()

        with patch('cogs.soundboard.asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.create_task = capture
            cog._reset_panel_timer(1)

        for c in captured:
            c.close()
        old_task.cancel.assert_called_once()

    async def test_reset_timer_creates_new_task(self, cog):
        captured = []
        new_task = MagicMock()

        def capture(coro):
            captured.append(coro)
            return new_task

        with patch('cogs.soundboard.asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.create_task = capture
            cog._reset_panel_timer(1)

        for c in captured:
            c.close()
        assert cog._panel_tasks[1] is new_task


# ---------------------------------------------------------------------------
# TestAskToJoin
# ---------------------------------------------------------------------------

class TestSbAskToJoin:
    async def test_timeout_returns_false(self, cog, ctx):
        msg = AsyncMock()
        msg.id = 42
        ctx.send = AsyncMock(return_value=msg)
        msg.add_reaction = AsyncMock()
        msg.remove_reaction = AsyncMock()
        msg.edit = AsyncMock()
        cog.bot.wait_for = AsyncMock(side_effect=asyncio.TimeoutError)

        result = await cog._ask_to_join(ctx)
        assert result is False
        assert 'timed out' in str(msg.edit.call_args).lower()

    async def test_yes_reaction_returns_true(self, cog, ctx):
        msg = AsyncMock()
        msg.id = 42
        ctx.send = AsyncMock(return_value=msg)
        msg.add_reaction = AsyncMock()
        msg.remove_reaction = AsyncMock()
        msg.edit = AsyncMock()

        reaction = MagicMock()
        reaction.emoji = '✅'
        reaction.message.id = 42
        cog.bot.wait_for = AsyncMock(return_value=(reaction, ctx.author))

        assert await cog._ask_to_join(ctx) is True

    async def test_no_reaction_returns_false(self, cog, ctx):
        msg = AsyncMock()
        msg.id = 42
        ctx.send = AsyncMock(return_value=msg)
        msg.add_reaction = AsyncMock()
        msg.remove_reaction = AsyncMock()
        msg.edit = AsyncMock()

        reaction = MagicMock()
        reaction.emoji = '❌'
        reaction.message.id = 42
        cog.bot.wait_for = AsyncMock(return_value=(reaction, ctx.author))

        assert await cog._ask_to_join(ctx) is False
