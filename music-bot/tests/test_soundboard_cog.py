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


# ---------------------------------------------------------------------------
# TestSbList
# ---------------------------------------------------------------------------

class TestSbList:
    async def test_empty_list(self, cog, ctx):
        await cog.sb_list.callback(cog, ctx)
        ctx.send.assert_called_once()
        assert 'No sounds' in ctx.send.call_args[0][0]

    async def test_list_shows_sounds(self, cog, ctx, sound_file):
        sbc.add_sound(ctx.guild.id, 'boom', '💥', str(sound_file), 'test source')
        await cog.sb_list.callback(cog, ctx)
        msg = ctx.send.call_args[0][0]
        assert 'boom' in msg
        assert '💥' in msg
        assert 'test source' in msg


# ---------------------------------------------------------------------------
# TestSbAdd
# ---------------------------------------------------------------------------

class TestSbAdd:
    async def test_add_no_attachment_no_query(self, cog, ctx):
        await cog.sb_add.callback(cog, ctx, 'boom', '💥', query=None)
        ctx.send.assert_called_once()
        assert 'Provide' in ctx.send.call_args[0][0]

    async def test_add_non_mp3_attachment(self, cog, ctx):
        attachment = MagicMock()
        attachment.filename = 'file.wav'
        ctx.message.attachments = [attachment]
        await cog.sb_add.callback(cog, ctx, 'boom', '💥', query=None)
        msg = ctx.send.call_args[0][0]
        assert 'MP3' in msg

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
        msg = ctx.send.call_args[0][0]
        assert 'Could not download' in msg


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
        msg = ctx.send.call_args[0][0]
        assert 'removed' in msg
        assert sbc.get_sound(ctx.guild.id, 'boom') is None

    async def test_remove_deletes_file(self, cog, ctx, sound_file):
        sbc.add_sound(ctx.guild.id, 'boom', '💥', str(sound_file), 'src')
        assert sound_file.exists()
        await cog.sb_remove.callback(cog, ctx, name='boom')
        assert not sound_file.exists()


# ---------------------------------------------------------------------------
# TestSbTrigger — voice checks
# ---------------------------------------------------------------------------

class TestSbTrigger:
    async def test_sound_not_found(self, cog, ctx):
        await cog.sb_trigger.callback(cog, ctx, name='ghost')
        assert 'No sound' in ctx.send.call_args[0][0]

    async def test_user_not_in_voice(self, cog, ctx_no_voice, sound_file):
        sbc.add_sound(ctx_no_voice.guild.id, 'boom', '💥', str(sound_file), 'src')
        await cog.sb_trigger.callback(cog, ctx_no_voice, name='boom')
        msg = ctx_no_voice.send.call_args[0][0]
        assert 'courage' in msg

    async def test_bot_busy_different_channel(self, cog, ctx, voice_client, mock_bot, sound_file):
        sbc.add_sound(ctx.guild.id, 'boom', '💥', str(sound_file), 'src')
        state = get_state(mock_bot, ctx.guild.id)
        state['voice_client'] = voice_client
        voice_client.channel = MagicMock()  # different channel from ctx.author.voice.channel
        await cog.sb_trigger.callback(cog, ctx, name='boom')
        msg = ctx.send.call_args[0][0]
        assert 'busy' in msg

    async def test_refuses_while_playing(self, cog, ctx_with_vc, voice_client, sound_file):
        sbc.add_sound(ctx_with_vc.guild.id, 'boom', '💥', str(sound_file), 'src')
        voice_client.is_playing.return_value = True
        await cog.sb_trigger.callback(cog, ctx_with_vc, name='boom')
        msg = ctx_with_vc.send.call_args[0][0]
        assert 'Cannot play' in msg

    async def test_refuses_while_paused(self, cog, ctx_with_vc, voice_client, sound_file):
        sbc.add_sound(ctx_with_vc.guild.id, 'boom', '💥', str(sound_file), 'src')
        voice_client.is_paused.return_value = True
        await cog.sb_trigger.callback(cog, ctx_with_vc, name='boom')
        msg = ctx_with_vc.send.call_args[0][0]
        assert 'Cannot play' in msg

    async def test_missing_file(self, cog, ctx_with_vc, tmp_path, sound_file):
        sbc.add_sound(ctx_with_vc.guild.id, 'boom', '💥', str(tmp_path / 'missing.mp3'), 'src')
        await cog.sb_trigger.callback(cog, ctx_with_vc, name='boom')
        msg = ctx_with_vc.send.call_args[0][0]
        assert 'missing' in msg

    async def test_plays_sound(self, cog, ctx_with_vc, voice_client, sound_file):
        sbc.add_sound(ctx_with_vc.guild.id, 'boom', '💥', str(sound_file), 'src')
        with patch('cogs.soundboard.discord.FFmpegPCMAudio', return_value=MagicMock()):
            await cog.sb_trigger.callback(cog, ctx_with_vc, name='boom')
        voice_client.play.assert_called_once()
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
             patch('cogs.soundboard.discord.FFmpegPCMAudio', return_value=MagicMock()):
            await cog.sb_trigger.callback(cog, ctx, name='boom')

        state = get_state(mock_bot, ctx.guild.id)
        assert state['voice_client'] is new_vc
        new_vc.play.assert_called_once()

    async def test_bot_not_in_voice_confirm_no(self, cog, ctx, sound_file, mock_bot):
        sbc.add_sound(ctx.guild.id, 'boom', '💥', str(sound_file), 'src')
        with patch.object(cog, '_ask_to_join', new=AsyncMock(return_value=False)):
            await cog.sb_trigger.callback(cog, ctx, name='boom')
        state = get_state(mock_bot, ctx.guild.id)
        assert state['voice_client'] is None


# ---------------------------------------------------------------------------
# TestAskToJoin (soundboard copy)
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
        msg.edit.assert_called_once()
        assert 'timed out' in msg.edit.call_args[1].get('content', '') or \
               'timed out' in str(msg.edit.call_args)

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

        result = await cog._ask_to_join(ctx)
        assert result is True

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

        result = await cog._ask_to_join(ctx)
        assert result is False
