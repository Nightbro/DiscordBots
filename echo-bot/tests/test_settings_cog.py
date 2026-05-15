import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.settings import SettingsCog, _format_bool, _settings_embed


# ---------------------------------------------------------------------------
# _format_bool
# ---------------------------------------------------------------------------

def test_format_bool_true():
    assert '✅' in _format_bool(True)


def test_format_bool_false():
    assert '❌' in _format_bool(False)


# ---------------------------------------------------------------------------
# _settings_embed
# ---------------------------------------------------------------------------

_ALL_SETTINGS = {
    'auto_join': False, 'auto_leave': True, 'notify_write': True, 'notify_say': False,
}


def test_settings_embed_contains_keys():
    with patch('cogs.settings.get_all_settings', return_value=_ALL_SETTINGS):
        embed = _settings_embed(123, 'Test Server')
    assert 'auto_join' in embed.description
    assert 'auto_leave' in embed.description
    assert 'notify_write' in embed.description
    assert 'notify_say' in embed.description


def test_settings_embed_marks_override():
    from utils.config import AUTO_JOIN
    overridden_value = not AUTO_JOIN
    overrides = {**_ALL_SETTINGS, 'auto_join': overridden_value}
    with patch('cogs.settings.get_all_settings', return_value=overrides):
        with patch('cogs.settings._GLOBAL_DEFAULTS', {**_ALL_SETTINGS, 'auto_join': AUTO_JOIN}):
            embed = _settings_embed(123, 'Test Server')
    assert 'overridden' in embed.description


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cog(mock_bot) -> SettingsCog:
    return SettingsCog(mock_bot)


def _admin_ctx(mock_bot):
    ctx = MagicMock()
    ctx.bot = mock_bot
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    ctx.guild.name = 'Test Server'
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.manage_guild = True
    ctx.send = AsyncMock()
    return ctx


# ---------------------------------------------------------------------------
# cog_check
# ---------------------------------------------------------------------------

async def test_cog_check_allows_manage_guild(mock_bot):
    cog = _cog(mock_bot)
    ctx = _admin_ctx(mock_bot)
    ctx.guild = MagicMock()
    result = await cog.cog_check(ctx)
    assert result is True


async def test_cog_check_denies_regular_user(mock_bot):
    cog = _cog(mock_bot)
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.manage_guild = False
    mock_bot.is_owner = AsyncMock(return_value=False)
    result = await cog.cog_check(ctx)
    assert result is False


async def test_cog_check_allows_bot_owner(mock_bot):
    cog = _cog(mock_bot)
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.manage_guild = False
    mock_bot.is_owner = AsyncMock(return_value=True)
    result = await cog.cog_check(ctx)
    assert result is True


# ---------------------------------------------------------------------------
# settings_set
# ---------------------------------------------------------------------------

async def test_settings_set_valid_key(mock_bot):
    cog = _cog(mock_bot)
    ctx = _admin_ctx(mock_bot)
    with patch('cogs.settings.set_setting') as mock_set:
        await cog.settings_set.callback(cog, ctx, key='auto_join', value=True)
    mock_set.assert_called_once_with(ctx.guild.id, 'auto_join', True)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


async def test_settings_set_invalid_key(mock_bot):
    cog = _cog(mock_bot)
    ctx = _admin_ctx(mock_bot)
    await cog.settings_set.callback(cog, ctx, key='nonexistent', value=True)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


# ---------------------------------------------------------------------------
# settings_reset
# ---------------------------------------------------------------------------

async def test_settings_reset_valid_key(mock_bot):
    cog = _cog(mock_bot)
    ctx = _admin_ctx(mock_bot)
    with patch('cogs.settings.reset_setting') as mock_reset:
        await cog.settings_reset.callback(cog, ctx, key='auto_leave')
    mock_reset.assert_called_once_with(ctx.guild.id, 'auto_leave')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


async def test_settings_reset_invalid_key(mock_bot):
    cog = _cog(mock_bot)
    ctx = _admin_ctx(mock_bot)
    await cog.settings_reset.callback(cog, ctx, key='bad_key')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


# ---------------------------------------------------------------------------
# settings_show
# ---------------------------------------------------------------------------

async def test_settings_show_sends_embed(mock_bot):
    cog = _cog(mock_bot)
    ctx = _admin_ctx(mock_bot)
    with patch('cogs.settings.get_all_settings', return_value=_ALL_SETTINGS):
        await cog.settings_show.callback(cog, ctx)
    ctx.send.assert_awaited_once()
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'auto_join' in embed.description
