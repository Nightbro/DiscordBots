import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.intros import IntrosCog, _trigger_label, _entry_lines


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cog(mock_bot) -> IntrosCog:
    return IntrosCog(mock_bot)


def _ctx_with_attachment(ctx, filename='intro.mp3'):
    attachment = MagicMock()
    attachment.filename = filename
    attachment.read = AsyncMock(return_value=b'audio data')
    ctx.message = MagicMock()
    ctx.message.attachments = [attachment]
    return ctx


def _ctx_no_attachment(ctx):
    ctx.message = MagicMock()
    ctx.message.attachments = []
    return ctx


# ---------------------------------------------------------------------------
# _trigger_label
# ---------------------------------------------------------------------------

def test_trigger_label_bot():
    label = _trigger_label('bot', {}, 0)
    assert 'bot' in label.lower() or '🤖' in label


def test_trigger_label_user():
    label = _trigger_label('user', {}, 0)
    assert 'user' in label.lower() or '👥' in label


def test_trigger_label_user_id_with_member_name():
    label = _trigger_label('user_12345', {'member_name': 'Alice'}, 0)
    assert 'Alice' in label


def test_trigger_label_user_id_fallback():
    label = _trigger_label('user_12345', {}, 0)
    assert '12345' in label


# ---------------------------------------------------------------------------
# _entry_lines
# ---------------------------------------------------------------------------

def test_entry_lines_default_only(tmp_path):
    f = tmp_path / 'intro.mp3'
    f.write_bytes(b'x')
    entry = {'default': {'file': str(f), 'source': 'test.mp3'}}
    lines = _entry_lines('bot', entry, 0)
    assert any('intro.mp3' in l for l in lines)


def test_entry_lines_with_schedule(tmp_path):
    f = tmp_path / 'intro.mp3'
    f.write_bytes(b'x')
    s = tmp_path / 'sched.mp3'
    s.write_bytes(b'x')
    entry = {
        'default': {'file': str(f), 'source': 'default.mp3'},
        'schedule': [{'days': 'MON', 'file': str(s), 'source': 'monday.mp3'}],
    }
    lines = _entry_lines('bot', entry, 0)
    assert any('default' in l for l in lines)
    assert any('MON' in l for l in lines)


def test_entry_lines_missing_file(tmp_path):
    entry = {'default': {'file': str(tmp_path / 'missing.mp3'), 'source': 'x'}}
    lines = _entry_lines('user', entry, 0)
    assert any('missing' in l for l in lines)


# ---------------------------------------------------------------------------
# intro_set
# ---------------------------------------------------------------------------

async def test_intro_set_no_attachment_no_query(mock_bot, ctx):
    cog = _cog(mock_bot)
    _ctx_no_attachment(ctx)
    with patch('cogs.intros.set_default_entry') as mock_set:
        await cog.intro_set.callback(cog, ctx, trigger='bot', query='')
    mock_set.assert_not_called()
    ctx.send.assert_awaited()


async def test_intro_set_with_attachment(mock_bot, ctx, tmp_path):
    cog = _cog(mock_bot)
    _ctx_with_attachment(ctx, 'intro.mp3')
    with patch('cogs.intros.INTRO_SOUNDS_DIR', tmp_path), \
         patch('cogs.intros.set_default_entry') as mock_set:
        await cog.intro_set.callback(cog, ctx, trigger='bot', query='')
    mock_set.assert_called_once()
    call_args = mock_set.call_args
    assert call_args[0][1] == 'bot'


async def test_intro_set_invalid_trigger(mock_bot, ctx):
    cog = _cog(mock_bot)
    _ctx_no_attachment(ctx)
    with patch('discord.ext.commands.MemberConverter.convert', side_effect=discord.ext.commands.MemberNotFound('unknown')):
        await cog.intro_set.callback(cog, ctx, trigger='unknown_trigger', query='')
    ctx.send.assert_awaited()


async def test_intro_set_unsupported_ext(mock_bot, ctx, tmp_path):
    cog = _cog(mock_bot)
    _ctx_with_attachment(ctx, 'intro.exe')
    with patch('cogs.intros.INTRO_SOUNDS_DIR', tmp_path), \
         patch('cogs.intros.set_default_entry') as mock_set:
        await cog.intro_set.callback(cog, ctx, trigger='bot', query='')
    mock_set.assert_not_called()


# ---------------------------------------------------------------------------
# intro_schedule
# ---------------------------------------------------------------------------

async def test_intro_schedule_invalid_days(mock_bot, ctx):
    cog = _cog(mock_bot)
    _ctx_no_attachment(ctx)
    await cog.intro_schedule.callback(cog, ctx, trigger='bot', days='BADDAY', query='')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_intro_schedule_valid(mock_bot, ctx, tmp_path):
    cog = _cog(mock_bot)
    _ctx_with_attachment(ctx, 'monday.mp3')
    with patch('cogs.intros.INTRO_SOUNDS_DIR', tmp_path), \
         patch('cogs.intros.set_schedule_entry') as mock_set:
        await cog.intro_schedule.callback(cog, ctx, trigger='bot', days='MON', query='')
    mock_set.assert_called_once()
    call_args = mock_set.call_args[0]
    assert 'MON' in call_args[2]


# ---------------------------------------------------------------------------
# intro_unschedule
# ---------------------------------------------------------------------------

async def test_intro_unschedule_invalid_days(mock_bot, ctx):
    cog = _cog(mock_bot)
    _ctx_no_attachment(ctx)
    await cog.intro_unschedule.callback(cog, ctx, trigger='bot', days='BADDAY')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_intro_unschedule_not_found(mock_bot, ctx):
    cog = _cog(mock_bot)
    _ctx_no_attachment(ctx)
    with patch('cogs.intros.remove_schedule_entry', return_value=False):
        await cog.intro_unschedule.callback(cog, ctx, trigger='bot', days='MON')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_intro_unschedule_success(mock_bot, ctx):
    cog = _cog(mock_bot)
    _ctx_no_attachment(ctx)
    with patch('cogs.intros.remove_schedule_entry', return_value=True):
        await cog.intro_unschedule.callback(cog, ctx, trigger='bot', days='MON')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


# ---------------------------------------------------------------------------
# intro_clear
# ---------------------------------------------------------------------------

async def test_intro_clear_no_config(mock_bot, ctx):
    cog = _cog(mock_bot)
    _ctx_no_attachment(ctx)
    with patch('cogs.intros.clear_trigger', return_value=None):
        await cog.intro_clear.callback(cog, ctx, trigger='bot')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'ℹ️' in embed.title


async def test_intro_clear_success(mock_bot, ctx):
    cog = _cog(mock_bot)
    _ctx_no_attachment(ctx)
    with patch('cogs.intros.clear_trigger', return_value={'default': {'file': '/x.mp3', 'source': 'x'}}):
        await cog.intro_clear.callback(cog, ctx, trigger='bot')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


# ---------------------------------------------------------------------------
# intro_rename
# ---------------------------------------------------------------------------

async def test_intro_rename_not_found(mock_bot, ctx):
    cog = _cog(mock_bot)
    _ctx_no_attachment(ctx)
    with patch('cogs.intros.rename_entry', return_value=False):
        await cog.intro_rename.callback(cog, ctx, trigger='bot', name='My Bot')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_intro_rename_success(mock_bot, ctx):
    cog = _cog(mock_bot)
    _ctx_no_attachment(ctx)
    with patch('cogs.intros.rename_entry', return_value=True):
        await cog.intro_rename.callback(cog, ctx, trigger='bot', name='My Bot')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


# ---------------------------------------------------------------------------
# intro_list
# ---------------------------------------------------------------------------

async def test_intro_list_empty(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.intros.list_entries', return_value={}):
        await cog.intro_list.callback(cog, ctx)
    ctx.send.assert_awaited_once()


async def test_intro_list_with_entries(mock_bot, ctx, tmp_path):
    cog = _cog(mock_bot)
    f = tmp_path / 'x.mp3'
    f.write_bytes(b'x')
    entries = {'bot': {'default': {'file': str(f), 'source': 'x.mp3'}}}
    with patch('cogs.intros.list_entries', return_value=entries):
        await cog.intro_list.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert embed.description


# ---------------------------------------------------------------------------
# intro_show
# ---------------------------------------------------------------------------

async def test_intro_show_empty(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.intros.list_entries', return_value={}):
        await cog.intro_show.callback(cog, ctx)
    ctx.send.assert_awaited_once()
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert embed.title


async def test_intro_show_with_bot_entry(mock_bot, ctx, tmp_path):
    cog = _cog(mock_bot)
    f = tmp_path / 'bot.mp3'
    f.write_bytes(b'x')
    entries = {'bot': {'default': {'file': str(f), 'source': 'bot.mp3'}}}
    with patch('cogs.intros.list_entries', return_value=entries):
        await cog.intro_show.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'bot.mp3' in (embed.description or '')


# ---------------------------------------------------------------------------
# intro_trigger
# ---------------------------------------------------------------------------

async def test_intro_trigger_no_voice(mock_bot, ctx_no_voice):
    cog = _cog(mock_bot)
    ctx_no_voice.message = MagicMock()
    ctx_no_voice.message.attachments = []
    await cog.intro_trigger.callback(cog, ctx_no_voice, trigger='bot')
    embed = ctx_no_voice.send.call_args.kwargs.get('embed') or ctx_no_voice.send.call_args.args[0]
    assert '❌' in embed.title


async def test_intro_trigger_no_file(mock_bot, ctx):
    cog = _cog(mock_bot)
    ctx.message = MagicMock()
    ctx.message.attachments = []
    with patch('cogs.intros.VoiceStreamer') as MockStreamer, \
         patch('cogs.intros.get_intro_file', return_value=None):
        mock_s = AsyncMock()
        MockStreamer.return_value = mock_s
        await cog.intro_trigger.callback(cog, ctx, trigger='bot')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_intro_trigger_plays(mock_bot, ctx, tmp_path):
    cog = _cog(mock_bot)
    ctx.message = MagicMock()
    ctx.message.attachments = []
    f = tmp_path / 'bot.mp3'
    f.write_bytes(b'x')
    with patch('cogs.intros.VoiceStreamer') as MockStreamer, \
         patch('cogs.intros.get_intro_file', return_value=f):
        mock_s = AsyncMock()
        MockStreamer.return_value = mock_s
        await cog.intro_trigger.callback(cog, ctx, trigger='bot')
    mock_s.interrupt.assert_awaited_once()


# ---------------------------------------------------------------------------
# intro_autojoin
# ---------------------------------------------------------------------------

async def test_intro_autojoin_on(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('utils.guild_config.set_setting') as mock_set:
        await cog.intro_autojoin.callback(cog, ctx, state='on')
    mock_set.assert_called_once_with(ctx.guild.id, 'auto_join', True)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


async def test_intro_autojoin_off(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('utils.guild_config.set_setting') as mock_set:
        await cog.intro_autojoin.callback(cog, ctx, state='off')
    mock_set.assert_called_once_with(ctx.guild.id, 'auto_join', False)


async def test_intro_autojoin_invalid(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('utils.guild_config.set_setting') as mock_set:
        await cog.intro_autojoin.callback(cog, ctx, state='maybe')
    mock_set.assert_not_called()
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


# ---------------------------------------------------------------------------
# on_voice_state_update
# ---------------------------------------------------------------------------

async def test_on_voice_state_update_plays_user_intro(mock_bot, guild_state):
    cog = _cog(mock_bot)
    member = MagicMock(spec=discord.Member)
    member.bot = False
    member.id = 123
    member.guild.id = 456

    channel = MagicMock(spec=discord.VoiceChannel)
    before = MagicMock()
    before.channel = None
    after = MagicMock()
    after.channel = channel

    with patch('cogs.intros.INTRO_ON_USER_JOIN', True), \
         patch.object(cog, '_play_user_intro', new=AsyncMock()) as mock_play:
        await cog.on_voice_state_update(member, before, after)
    mock_play.assert_awaited_once_with(456, 123, channel)


async def test_on_voice_state_update_ignores_other_bots(mock_bot, guild_state):
    cog = _cog(mock_bot)
    member = MagicMock(spec=discord.Member)
    member.bot = True
    member.id = 999  # Not the bot itself

    before = MagicMock()
    after = MagicMock()
    after.channel = MagicMock()

    with patch.object(cog, '_play_user_intro', new=AsyncMock()) as mock_play, \
         patch.object(cog, '_play_intro', new=AsyncMock()) as mock_bot_play:
        await cog.on_voice_state_update(member, before, after)
    mock_play.assert_not_awaited()
    mock_bot_play.assert_not_awaited()


async def test_on_voice_state_update_bot_join_plays_intro(mock_bot, guild_state):
    cog = _cog(mock_bot)
    member = MagicMock(spec=discord.Member)
    member.bot = True
    member.id = mock_bot.user.id  # The bot itself
    member.guild.id = 456

    channel = MagicMock(spec=discord.VoiceChannel)
    before = MagicMock()
    before.channel = None
    after = MagicMock()
    after.channel = channel

    with patch('cogs.intros.INTRO_ON_BOT_JOIN', True), \
         patch.object(cog, '_play_intro', new=AsyncMock()) as mock_play:
        await cog.on_voice_state_update(member, before, after)
    mock_play.assert_awaited_once_with(456, 'bot')


async def test_on_voice_state_update_user_join_disabled(mock_bot, guild_state):
    cog = _cog(mock_bot)
    member = MagicMock(spec=discord.Member)
    member.bot = False
    member.id = 123
    member.guild.id = 456

    channel = MagicMock(spec=discord.VoiceChannel)
    before = MagicMock()
    before.channel = None
    after = MagicMock()
    after.channel = channel

    with patch('cogs.intros.INTRO_ON_USER_JOIN', False), \
         patch.object(cog, '_play_user_intro', new=AsyncMock()) as mock_play:
        await cog.on_voice_state_update(member, before, after)
    mock_play.assert_not_awaited()
