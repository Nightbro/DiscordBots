from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.devlog import DevlogCog
from utils import devlog


@pytest.fixture(autouse=True)
def devlog_file(tmp_path):
    with patch('utils.config.DEVLOG_CONFIG_FILE', tmp_path / 'devlog_config.json'):
        yield


@pytest.fixture
def cog(mock_bot):
    return DevlogCog(mock_bot)


@pytest.fixture
def gctx(ctx):
    ctx.channel = MagicMock()
    ctx.channel.id = 4242
    ctx.guild.name = 'Test Server'
    ctx.author.send = AsyncMock()
    return ctx


@pytest.fixture
def not_owner_admin(mock_bot, gctx):
    mock_bot.is_owner = AsyncMock(return_value=False)
    gctx.author.guild_permissions = MagicMock(manage_guild=True)
    return gctx


@pytest.fixture
def dm_ctx(gctx):
    gctx.guild = None
    return gctx


async def run(cog, ctx, action='', scope=''):
    await cog.devlog_cmd.callback(cog, ctx, action, scope)
    return ctx.send.await_args.kwargs['embed']


# ---------------------------------------------------------------------------
# In a server
# ---------------------------------------------------------------------------

async def test_status_off_by_default(cog, gctx):
    embed = await run(cog, gctx)
    assert 'Off' in embed.description


async def test_here_sets_this_channel(cog, not_owner_admin):
    await run(cog, not_owner_admin, 'here')
    assert devlog.get_guild_target(123456789) == {'kind': 'channel', 'id': 4242, 'all': False}


async def test_status_shows_channel_when_on(cog, gctx):
    await run(cog, gctx, 'here')
    embed = await run(cog, gctx)
    assert '<#4242>' in embed.description


async def test_dm_sends_welcome_and_sets_dm_target(cog, not_owner_admin):
    await run(cog, not_owner_admin, 'dm')
    not_owner_admin.author.send.assert_awaited_once()
    assert devlog.get_guild_target(123456789) == {'kind': 'dm', 'id': 555555555, 'all': False}


async def test_dm_blocked_does_not_enable(cog, gctx):
    gctx.author.send.side_effect = discord.Forbidden(MagicMock(status=403), 'Cannot send')
    embed = await run(cog, gctx, 'dm')
    assert '❌' in embed.title
    assert devlog.get_guild_target(123456789) is None


async def test_off_turns_it_off(cog, gctx):
    await run(cog, gctx, 'here')
    await run(cog, gctx, 'off')
    assert devlog.get_guild_target(123456789) is None


async def test_off_when_already_off(cog, gctx):
    embed = await run(cog, gctx, 'off')
    assert 'already' in embed.title


async def test_requires_manage_server(cog, mock_bot, gctx):
    mock_bot.is_owner = AsyncMock(return_value=False)
    gctx.author.guild_permissions = MagicMock(manage_guild=False)
    embed = await run(cog, gctx, 'here')
    assert 'Manage Server' in embed.title
    assert devlog.get_guild_target(123456789) is None


async def test_status_allowed_without_manage_server(cog, mock_bot, gctx):
    mock_bot.is_owner = AsyncMock(return_value=False)
    gctx.author.guild_permissions = MagicMock(manage_guild=False)
    embed = await run(cog, gctx)
    assert 'Off' in embed.description


async def test_all_is_owner_only(cog, not_owner_admin):
    embed = await run(cog, not_owner_admin, 'here', 'all')
    assert 'owner' in embed.title
    assert devlog.get_guild_target(123456789) is None


async def test_owner_here_all(cog, gctx):
    await run(cog, gctx, 'here', 'all')
    assert devlog.get_guild_target(123456789)['all'] is True
    assert devlog.targets_for(None) == [('channel', 4242)]


async def test_bad_scope_shows_usage(cog, gctx):
    embed = await run(cog, gctx, 'here', 'everything')
    assert '!devlog here' in embed.description
    assert devlog.get_guild_target(123456789) is None


async def test_unknown_action_shows_usage(cog, gctx):
    embed = await run(cog, gctx, 'banana')
    assert '!devlog here' in embed.description


async def test_test_action_logs_a_warning(cog, gctx, caplog):
    with caplog.at_level('WARNING', logger='cogs.devlog'):
        await run(cog, gctx, 'test')
    assert any('Dev log test' in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# In a DM
# ---------------------------------------------------------------------------

async def test_dm_here_subscribes_owner_to_everything(cog, dm_ctx):
    await run(cog, dm_ctx, 'here', 'all')
    assert devlog.get_owner_dm() == 555555555
    assert devlog.targets_for(None) == [('dm', 555555555)]
    assert devlog.targets_for(987) == [('dm', 555555555)]


async def test_dm_here_without_all_also_subscribes(cog, dm_ctx):
    await run(cog, dm_ctx, 'here')
    assert devlog.get_owner_dm() == 555555555


async def test_dm_status_and_off(cog, dm_ctx):
    embed = await run(cog, dm_ctx)
    assert 'Off' in embed.description
    await run(cog, dm_ctx, 'here')
    embed = await run(cog, dm_ctx)
    assert 'every error' in embed.description
    await run(cog, dm_ctx, 'off')
    assert devlog.get_owner_dm() is None


async def test_dm_non_owner_rejected(cog, mock_bot, dm_ctx):
    mock_bot.is_owner = AsyncMock(return_value=False)
    embed = await run(cog, dm_ctx, 'here')
    assert 'owner' in embed.title
    assert devlog.get_owner_dm() is None
