import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.intros import IntrosCog, _trigger_label, _entry_lines


# ---------------------------------------------------------------------------
# _trigger_label
# ---------------------------------------------------------------------------

def test_trigger_label_empty():
    assert _trigger_label({}) == 'No intro set.'


def test_trigger_label_default_only():
    label = _trigger_label({'default': 'intro.mp3'})
    assert 'intro.mp3' in label


def test_trigger_label_with_schedule():
    entry = {'default': 'intro.mp3', 'schedule': {'mon': 'weekday.mp3'}}
    label = _trigger_label(entry)
    assert 'schedule' in label
    assert 'mon' in label


def test_trigger_label_with_override():
    entry = {'overrides': {'2024-12-25': 'xmas.mp3'}}
    label = _trigger_label(entry)
    assert '2024-12-25' in label


# ---------------------------------------------------------------------------
# _entry_lines
# ---------------------------------------------------------------------------

def test_entry_lines_formats_member_name():
    guild = MagicMock()
    member = MagicMock()
    member.display_name = 'Alice'
    guild.get_member.return_value = member

    lines = _entry_lines({'111': {'default': 'intro.mp3'}}, guild)
    assert any('Alice' in l for l in lines)


def test_entry_lines_handles_missing_member():
    guild = MagicMock()
    guild.get_member.return_value = None
    lines = _entry_lines({'999': {'default': 'intro.mp3'}}, guild)
    assert any('999' in l for l in lines)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _cog(mock_bot) -> IntrosCog:
    return IntrosCog(mock_bot)


async def test_intro_clear_no_config(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.intros.clear_trigger', return_value=False):
        await cog.intro_clear.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'ℹ️' in embed.title


async def test_intro_clear_success(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.intros.clear_trigger', return_value=True):
        await cog.intro_clear.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


async def test_intro_show_no_entry(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.intros.get_user_entry', return_value={}):
        await cog.intro_show.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'ℹ️' in embed.title


async def test_intro_show_with_entry(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.intros.get_user_entry', return_value={'default': 'intro.mp3'}):
        await cog.intro_show.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'ℹ️' in embed.title
    assert 'intro.mp3' in embed.description


async def test_intro_trigger_no_voice(mock_bot, ctx_no_voice):
    cog = _cog(mock_bot)
    await cog.intro_trigger.callback(cog, ctx_no_voice)
    ctx_no_voice.send.assert_awaited_once()
    embed = ctx_no_voice.send.call_args.kwargs.get('embed') or ctx_no_voice.send.call_args.args[0]
    assert '❌' in embed.title


async def test_intro_trigger_no_file(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.intros.VoiceStreamer') as MockStreamer:
        mock_streamer = AsyncMock()
        MockStreamer.return_value = mock_streamer
        with patch('cogs.intros.get_intro_file', return_value=None):
            await cog.intro_trigger.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_intro_autojoin_enable(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.intros.set_auto_join') as mock_set:
        await cog.intro_autojoin.callback(cog, ctx, enabled=True)
    mock_set.assert_called_once_with(ctx.author.id, True)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


async def test_intro_schedule_invalid_days(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.intros.parse_days', return_value=[]):
        await cog.intro_schedule.callback(cog, ctx, days='invalid')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_on_voice_state_update_plays_intro(mock_bot, guild_state):
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

    with patch('cogs.intros.INTRO_ON_USER_JOIN', True):
        with patch.object(cog, '_play_intro', new=AsyncMock()) as mock_play:
            await cog.on_voice_state_update(member, before, after)
    mock_play.assert_awaited_once()


async def test_on_voice_state_update_ignores_bots(mock_bot, guild_state):
    cog = _cog(mock_bot)
    member = MagicMock(spec=discord.Member)
    member.bot = True

    before = MagicMock()
    after = MagicMock()
    after.channel = MagicMock()

    with patch.object(cog, '_play_intro', new=AsyncMock()) as mock_play:
        await cog.on_voice_state_update(member, before, after)
    mock_play.assert_not_awaited()
