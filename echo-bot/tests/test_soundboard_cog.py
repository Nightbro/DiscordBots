import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.soundboard import SoundboardCog, _EMOJI_RE, _parse_add_text
from utils.soundboard_config import DEFAULT_EMOJI


# ---------------------------------------------------------------------------
# _parse_add_text
# ---------------------------------------------------------------------------

BOOM = '\U0001f4a5'
BELL = '\U0001f514'


def test_parse_add_text_name_emoji_short():
    assert _parse_add_text(f'explosion effect {BOOM} | ex') == ('explosion effect', BOOM, 'ex')


def test_parse_add_text_name_emoji_no_short():
    assert _parse_add_text(f'boom {BOOM}') == ('boom', BOOM, '')


def test_parse_add_text_name_only():
    """The emoji is optional now — a bare name is valid."""
    assert _parse_add_text('no emoji here') == ('no emoji here', '', '')


def test_parse_add_text_multi_word_name_with_short():
    assert _parse_add_text('epic fail sound | ef') == ('epic fail sound', '', 'ef')


def test_parse_add_text_emoji_inside_name_is_lifted_out():
    assert _parse_add_text(f'epic {BOOM} fail') == ('epic fail', BOOM, '')


def test_parse_add_text_custom_discord_emoji():
    assert _parse_add_text('boom <a:custom:123> | b') == ('boom', '<a:custom:123>', 'b')


def test_parse_add_text_collapses_whitespace():
    assert _parse_add_text('  epic    fail  |   ef  ') == ('epic fail', '', 'ef')


def test_parse_add_text_empty_name():
    assert _parse_add_text(f'{BOOM} | short') == ('', BOOM, 'short')


def test_parse_add_text_empty_text():
    assert _parse_add_text('   ') == ('', '', '')


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

async def test_sb_add_without_emoji_takes_one_from_the_pool(mock_bot, ctx, tmp_path):
    ctx.message = MagicMock()
    att = MagicMock()
    att.filename = 'epic fail.mp3'
    att.save = AsyncMock()
    ctx.message.attachments = [att]

    cog = _cog(mock_bot)
    with patch('cogs.soundboard.sound_exists', return_value=False),          patch('cogs.soundboard.next_free_emoji', return_value=BELL),          patch('cogs.soundboard.add_sound') as mock_add,          patch('cogs.soundboard.SOUNDBOARD_DIR', tmp_path):
        await cog.sb_add.callback(cog, ctx, text='epic fail sound')
    mock_add.assert_called_once_with('epic fail sound', 'epic fail sound.mp3', BELL, 'epicfailsound')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


async def test_sb_add_warns_when_emoji_pool_is_exhausted(mock_bot, ctx, tmp_path):
    ctx.message = MagicMock()
    att = MagicMock()
    att.filename = 'x.mp3'
    att.save = AsyncMock()
    ctx.message.attachments = [att]

    cog = _cog(mock_bot)
    with patch('cogs.soundboard.sound_exists', return_value=False),          patch('cogs.soundboard.next_free_emoji', return_value=None),          patch('cogs.soundboard.add_sound') as mock_add,          patch('cogs.soundboard.SOUNDBOARD_DIR', tmp_path):
        await cog.sb_add.callback(cog, ctx, text='last one')
    assert mock_add.call_args.args[2] == DEFAULT_EMOJI
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'taken' in embed.description


async def test_sb_add_empty_name_sends_error(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.sb_add.callback(cog, ctx, text=f'{BOOM} short')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_sb_add_duplicate_sends_error(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.sound_exists', return_value=True):
        await cog.sb_add.callback(cog, ctx, text=f'boom {BOOM}')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_sb_add_success_auto_short(mock_bot, ctx, tmp_path):
    ctx.message = MagicMock()
    att = MagicMock()
    att.filename = 'explosion effect.mp3'
    att.save = AsyncMock()
    ctx.message.attachments = [att]

    cog = _cog(mock_bot)
    with patch('cogs.soundboard.sound_exists', return_value=False):
        with patch('cogs.soundboard.add_sound') as mock_add:
            with patch('cogs.soundboard.SOUNDBOARD_DIR', tmp_path):
                await cog.sb_add.callback(cog, ctx, text=f'explosion effect {BOOM}')
    mock_add.assert_called_once_with('explosion effect', 'explosion effect.mp3', BOOM, 'explosioneffect')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title
    assert '!explosioneffect' in embed.description


async def test_sb_add_success_explicit_short(mock_bot, ctx, tmp_path):
    ctx.message = MagicMock()
    att = MagicMock()
    att.filename = 'explosion effect.mp3'
    att.save = AsyncMock()
    ctx.message.attachments = [att]

    cog = _cog(mock_bot)
    with patch('cogs.soundboard.sound_exists', return_value=False):
        with patch('cogs.soundboard.add_sound') as mock_add:
            with patch('cogs.soundboard.SOUNDBOARD_DIR', tmp_path):
                await cog.sb_add.callback(cog, ctx, text=f'explosion effect {BOOM} | ex')
    mock_add.assert_called_once_with('explosion effect', 'explosion effect.mp3', BOOM, 'ex')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '!ex' in embed.description


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
# sb_short
# ---------------------------------------------------------------------------

async def test_sb_short_missing_short_arg_sends_error(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.sb_short.callback(cog, ctx, text='boom')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_sb_short_sound_not_found(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.sound_exists', return_value=False):
        await cog.sb_short.callback(cog, ctx, text='missing ex')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_sb_short_success(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.sound_exists', return_value=True):
        with patch('cogs.soundboard.set_short') as mock_set:
            await cog.sb_short.callback(cog, ctx, text='explosion effect ex')
    mock_set.assert_called_once_with('explosion effect', 'ex')
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


# ---------------------------------------------------------------------------
# on_message — quick trigger (!soundname)
# ---------------------------------------------------------------------------

def _make_message(content: str, *, bot_author: bool = False, guild=True, in_voice: bool = True):
    msg = MagicMock(spec=discord.Message)
    msg.content = content
    msg.guild = MagicMock() if guild else None
    if guild:
        msg.guild.id = 111
    author = MagicMock(spec=discord.Member)
    author.bot = bot_author
    if in_voice:
        author.voice = MagicMock()
        author.voice.channel = MagicMock()
    else:
        author.voice = None
    msg.author = author
    msg.channel = AsyncMock()
    return msg


async def test_quick_trigger_ignored_for_bot(mock_bot):
    cog = _cog(mock_bot)
    msg = _make_message('!boom', bot_author=True)
    with patch('cogs.soundboard.find_sound', return_value=('boom', {'emoji': '💥', 'file': 'boom.mp3'})):
        await cog.on_message(msg)
    msg.channel.send.assert_not_called()


async def test_quick_trigger_ignored_for_dm(mock_bot):
    cog = _cog(mock_bot)
    msg = _make_message('!boom', guild=False)
    with patch('cogs.soundboard.find_sound', return_value=('boom', {'emoji': '💥', 'file': 'boom.mp3'})):
        await cog.on_message(msg)
    msg.channel.send.assert_not_called()


async def test_quick_trigger_ignored_for_registered_command(mock_bot):
    cog = _cog(mock_bot)
    msg = _make_message('!sb')
    mock_bot.get_command = MagicMock(return_value=MagicMock())
    with patch('cogs.soundboard.find_sound', return_value=('sb', {'emoji': '🔊', 'file': 'sb.mp3'})):
        await cog.on_message(msg)
    msg.channel.send.assert_not_called()


async def test_quick_trigger_ignored_for_unknown_sound(mock_bot):
    cog = _cog(mock_bot)
    msg = _make_message('!notasound')
    mock_bot.get_command = MagicMock(return_value=None)
    with patch('cogs.soundboard.find_sound', return_value=None):
        await cog.on_message(msg)
    msg.channel.send.assert_not_called()


async def test_quick_trigger_no_voice_sends_error(mock_bot):
    cog = _cog(mock_bot)
    msg = _make_message('!boom', in_voice=False)
    mock_bot.get_command = MagicMock(return_value=None)
    with patch('cogs.soundboard.find_sound', return_value=('boom', {'emoji': '💥', 'file': 'boom.mp3'})):
        await cog.on_message(msg)
    msg.channel.send.assert_awaited_once()
    embed = msg.channel.send.call_args.kwargs.get('embed') or msg.channel.send.call_args.args[0]
    assert '❌' in embed.title


async def test_quick_trigger_plays_sound(mock_bot, tmp_path):
    cog = _cog(mock_bot)
    msg = _make_message('!boom')
    mock_bot.get_command = MagicMock(return_value=None)
    f = tmp_path / 'boom.mp3'
    f.write_bytes(b'')
    with patch('cogs.soundboard.find_sound', return_value=('boom', {'emoji': '💥', 'file': 'boom.mp3'})):
        with patch('cogs.soundboard.VoiceStreamer') as MockStreamer:
            mock_streamer = AsyncMock()
            MockStreamer.return_value = mock_streamer
            with patch('cogs.soundboard.get_sound_path', return_value=f):
                await cog.on_message(msg)
    mock_streamer.interrupt.assert_awaited_once()


async def test_quick_trigger_case_insensitive(mock_bot, tmp_path):
    cog = _cog(mock_bot)
    msg = _make_message('!BOOM')
    mock_bot.get_command = MagicMock(return_value=None)
    f = tmp_path / 'boom.mp3'
    f.write_bytes(b'')
    with patch('cogs.soundboard.find_sound', return_value=('boom', {'emoji': '💥', 'file': 'boom.mp3'})):
        with patch('cogs.soundboard.VoiceStreamer') as MockStreamer:
            mock_streamer = AsyncMock()
            MockStreamer.return_value = mock_streamer
            with patch('cogs.soundboard.get_sound_path', return_value=f):
                await cog.on_message(msg)
    mock_streamer.interrupt.assert_awaited_once()


async def test_quick_trigger_via_short_name(mock_bot, tmp_path):
    cog = _cog(mock_bot)
    msg = _make_message('!b')
    mock_bot.get_command = MagicMock(return_value=None)
    f = tmp_path / 'boom.mp3'
    f.write_bytes(b'')
    with patch('cogs.soundboard.find_sound', return_value=('boom', {'emoji': '💥', 'file': 'boom.mp3', 'short': 'b'})):
        with patch('cogs.soundboard.VoiceStreamer') as MockStreamer:
            mock_streamer = AsyncMock()
            MockStreamer.return_value = mock_streamer
            with patch('cogs.soundboard.get_sound_path', return_value=f):
                await cog.on_message(msg)
    mock_streamer.interrupt.assert_awaited_once()


# ---------------------------------------------------------------------------
# Multi-word names
# ---------------------------------------------------------------------------

async def test_sb_play_accepts_multi_word_name(mock_bot, ctx, tmp_path):
    sound_file = tmp_path / 'epic fail.mp3'
    sound_file.write_bytes(b'x')
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.VoiceStreamer') as MockStreamer, \
         patch('cogs.soundboard.get_sound_path', return_value=sound_file) as mock_path:
        streamer = AsyncMock()
        MockStreamer.return_value = streamer
        await cog.sb_play.callback(cog, ctx, name='epic fail sound')
    mock_path.assert_called_once_with('epic fail sound')
    assert streamer.interrupt.await_args.args[0].file_path == sound_file


async def test_sb_remove_accepts_multi_word_name(mock_bot, ctx, tmp_path):
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.get_sound', return_value={'file': 'epic fail.mp3'}), \
         patch('cogs.soundboard.remove_sound') as mock_remove, \
         patch('cogs.soundboard.SOUNDBOARD_DIR', tmp_path):
        await cog.sb_remove.callback(cog, ctx, name='epic fail sound')
    mock_remove.assert_called_once_with('epic fail sound')


def _trigger_message(content: str) -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.content = content
    message.author = MagicMock(spec=discord.Member)
    message.author.bot = False
    message.author.voice = MagicMock()
    message.guild = MagicMock()
    message.guild.id = 123456789
    message.channel = MagicMock()
    message.channel.send = AsyncMock()
    return message


async def test_quick_trigger_matches_multi_word_name(mock_bot, tmp_path):
    """!epic fail sound plays the sound whose name has spaces."""
    sound_file = tmp_path / 'epic.mp3'
    sound_file.write_bytes(b'x')
    mock_bot.get_command = MagicMock(return_value=None)
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.find_sound') as mock_find, \
         patch('cogs.soundboard.get_sound_path', return_value=sound_file), \
         patch('cogs.soundboard.VoiceStreamer') as MockStreamer:
        mock_find.side_effect = lambda q: ('epic fail sound', {}) if q == 'epic fail sound' else None
        streamer = AsyncMock()
        MockStreamer.return_value = streamer
        await cog.on_message(_trigger_message('!epic fail sound'))
    streamer.interrupt.assert_awaited_once()


async def test_quick_trigger_falls_back_to_first_word(mock_bot, tmp_path):
    """!boom now plays even when extra words follow."""
    sound_file = tmp_path / 'boom.mp3'
    sound_file.write_bytes(b'x')
    mock_bot.get_command = MagicMock(return_value=None)
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.find_sound') as mock_find, \
         patch('cogs.soundboard.get_sound_path', return_value=sound_file), \
         patch('cogs.soundboard.VoiceStreamer') as MockStreamer:
        mock_find.side_effect = lambda q: ('boom', {}) if q == 'boom' else None
        streamer = AsyncMock()
        MockStreamer.return_value = streamer
        await cog.on_message(_trigger_message('!boom loud'))
    streamer.interrupt.assert_awaited_once()


async def test_quick_trigger_ignores_registered_commands(mock_bot):
    mock_bot.get_command = MagicMock(return_value=MagicMock())  # 'play' is a real command
    cog = _cog(mock_bot)
    with patch('cogs.soundboard.find_sound') as mock_find:
        await cog.on_message(_trigger_message('!play some song'))
    mock_find.assert_not_called()
