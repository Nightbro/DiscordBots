import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.soundboard import SoundboardCog, _pick_emoji


# ---------------------------------------------------------------------------
# _pick_emoji
# ---------------------------------------------------------------------------

def test_pick_emoji_avoids_used():
    sounds = {'a': {'emoji': '🔊'}, 'b': {'emoji': '💥'}}
    emoji = _pick_emoji(sounds)
    assert emoji not in ('🔊', '💥')


def test_pick_emoji_empty_pool_fallback():
    # All pool emojis used — should fall back to '🔊'
    from cogs.soundboard import _EMOJI_POOL
    sounds = {str(i): {'emoji': e} for i, e in enumerate(_EMOJI_POOL)}
    emoji = _pick_emoji(sounds)
    assert emoji == '🔊'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cog(mock_bot) -> SoundboardCog:
    return SoundboardCog(mock_bot)


# ---------------------------------------------------------------------------
# sb_list
# ---------------------------------------------------------------------------

async def test_sb_list_empty(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.get_sounds', return_value={}):
        await cog.sb_list.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'No sounds' in embed.description


async def test_sb_list_with_sounds(mock_bot, ctx):
    sounds = {'boom': {'emoji': '💥', 'file': 'boom.mp3'}}
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.get_sounds', return_value=sounds):
        await cog.sb_list.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'boom' in embed.description


# ---------------------------------------------------------------------------
# sb_add
# ---------------------------------------------------------------------------

async def test_sb_add_duplicate_sends_error(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.sound_exists', return_value=True):
        await cog.sb_add.callback(cog, ctx, name='boom')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_sb_add_success(mock_bot, ctx, tmp_path):
    ctx.message = MagicMock()
    att = MagicMock()
    att.filename = 'boom.mp3'
    att.save = AsyncMock()
    ctx.message.attachments = [att]

    cog = _cog(mock_bot)
    with patch('cogs.soundboard.sound_exists', return_value=False):
        with patch('cogs.soundboard.get_sounds', return_value={}):
            with patch('cogs.soundboard.add_sound') as mock_add:
                with patch('cogs.soundboard.SOUNDBOARD_DIR', tmp_path):
                    await cog.sb_add.callback(cog, ctx, name='boom')
    mock_add.assert_called_once()
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


# ---------------------------------------------------------------------------
# sb_remove
# ---------------------------------------------------------------------------

async def test_sb_remove_not_found(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.get_sound', return_value=None):
        await cog.sb_remove.callback(cog, ctx, name='missing')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_sb_remove_success(mock_bot, ctx, tmp_path):
    cog = _cog(mock_bot)
    f = tmp_path / 'boom.mp3'
    f.write_bytes(b'')
    with patch('cogs.soundboard.get_sound', return_value={'emoji': '💥', 'file': 'boom.mp3'}):
        with patch('cogs.soundboard.remove_sound'):
            with patch('cogs.soundboard.SOUNDBOARD_DIR', tmp_path):
                await cog.sb_remove.callback(cog, ctx, name='boom')
    assert not f.exists()
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


# ---------------------------------------------------------------------------
# sb_play
# ---------------------------------------------------------------------------

async def test_sb_play_no_voice(mock_bot, ctx_no_voice):
    cog = _cog(mock_bot)
    await cog.sb_play.callback(cog, ctx_no_voice, name='boom')
    embed = ctx_no_voice.send.call_args.kwargs.get('embed') or ctx_no_voice.send.call_args.args[0]
    assert '❌' in embed.title


async def test_sb_play_sound_missing_file(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.VoiceStreamer') as MockStreamer:
        mock_streamer = AsyncMock()
        MockStreamer.return_value = mock_streamer
        with patch('cogs.soundboard.get_sound_path', return_value=None):
            await cog.sb_play.callback(cog, ctx, name='boom')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_sb_play_success(mock_bot, ctx, tmp_path):
    f = tmp_path / 'boom.mp3'
    f.write_bytes(b'')
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.VoiceStreamer') as MockStreamer:
        mock_streamer = AsyncMock()
        MockStreamer.return_value = mock_streamer
        with patch('cogs.soundboard.get_sound_path', return_value=f):
            await cog.sb_play.callback(cog, ctx, name='boom')
    mock_streamer.interrupt.assert_awaited_once()


# ---------------------------------------------------------------------------
# on_raw_reaction_add
# ---------------------------------------------------------------------------

async def test_reaction_ignored_for_bot(mock_bot):
    cog = _cog(mock_bot)
    mock_bot.user.id = 999

    payload = MagicMock(spec=discord.RawReactionActionEvent)
    payload.user_id = 999  # same as bot
    payload.message_id = 1

    await cog.on_raw_reaction_add(payload)
    # Nothing should happen — no error means success


async def test_reaction_ignored_for_unknown_panel(mock_bot):
    cog = _cog(mock_bot)
    payload = MagicMock(spec=discord.RawReactionActionEvent)
    payload.user_id = 123
    payload.message_id = 9999  # not in _panel_messages

    await cog.on_raw_reaction_add(payload)


async def test_reaction_plays_sound(mock_bot):
    cog = _cog(mock_bot)
    cog._panel_messages[42] = 111  # guild_id = 111

    sounds = {'boom': {'emoji': '💥', 'file': 'boom.mp3'}}
    guild = MagicMock()
    member = MagicMock()
    member.bot = False
    member.voice = MagicMock()
    member.voice.channel = MagicMock()
    guild.get_member.return_value = member
    mock_bot.get_guild = MagicMock(return_value=guild)

    channel = AsyncMock()
    msg = AsyncMock()
    channel.fetch_message = AsyncMock(return_value=msg)
    guild.get_channel = MagicMock(return_value=channel)

    payload = MagicMock(spec=discord.RawReactionActionEvent)
    payload.user_id = 123
    payload.message_id = 42
    payload.emoji = MagicMock()
    payload.emoji.__str__ = lambda self: '💥'
    payload.channel_id = 77
    mock_bot.user.id = 999

    with patch('cogs.soundboard.get_sounds', return_value=sounds):
        with patch('cogs.soundboard.VoiceStreamer') as MockStreamer:
            mock_streamer = AsyncMock()
            MockStreamer.return_value = mock_streamer
            with patch('cogs.soundboard.get_sound_path', return_value=MagicMock()):
                await cog.on_raw_reaction_add(payload)

    mock_streamer.interrupt.assert_awaited_once()
