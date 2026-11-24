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


# ---------------------------------------------------------------------------
# !devlog tail
# ---------------------------------------------------------------------------

_TS = '2024-01-15 12:00:00'


def _error_log(tmp_path, lines: list[str]) -> None:
    log_file = tmp_path / 'errors_20240115_120000.log'
    log_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _log_line(level: str, msg: str) -> str:
    return f'{_TS} [{level.ljust(8)}] utils.test: {msg}'


async def test_tail_non_owner_is_silent(cog, gctx, tmp_path):
    cog.bot.is_owner = AsyncMock(return_value=False)
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        await cog.devlog_tail.callback(cog, gctx, level='error', n=50)
    gctx.send.assert_not_awaited()


async def test_tail_no_files_shows_info(cog, gctx, tmp_path):
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        await cog.devlog_tail.callback(cog, gctx, level='error', n=50)
    embed = gctx.send.await_args.kwargs['embed']
    assert 'ℹ' in embed.title


async def test_tail_invalid_level_shows_error(cog, gctx, tmp_path):
    _error_log(tmp_path, [_log_line('ERROR', 'boom')])
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        await cog.devlog_tail.callback(cog, gctx, level='banana', n=50)
    embed = gctx.send.await_args.kwargs['embed']
    assert '❌' in embed.title


async def test_tail_returns_records_as_embed(cog, gctx, tmp_path):
    _error_log(tmp_path, [
        _log_line('ERROR', 'first failure'),
        _log_line('ERROR', 'second failure'),
    ])
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        await cog.devlog_tail.callback(cog, gctx, level='error', n=50)
    embed = gctx.send.await_args.kwargs['embed']
    assert 'first failure' in embed.description
    assert 'second failure' in embed.description


async def test_tail_empty_result_shows_info(cog, gctx, tmp_path):
    _error_log(tmp_path, [_log_line('WARNING', 'just a warning')])
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        await cog.devlog_tail.callback(cog, gctx, level='critical', n=50)
    embed = gctx.send.await_args.kwargs['embed']
    assert 'ℹ' in embed.title


async def test_tail_large_output_uploads_file(cog, gctx, tmp_path):
    # 200 error records will exceed the 3800-char embed limit
    lines = [_log_line('ERROR', 'x' * 30 + f' record {i}') for i in range(200)]
    _error_log(tmp_path, lines)
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        await cog.devlog_tail.callback(cog, gctx, level='error', n=200)
    call_kwargs = gctx.send.await_args.kwargs
    assert 'file' in call_kwargs
    assert isinstance(call_kwargs['file'], MagicMock.__class__) or hasattr(call_kwargs['file'], 'fp')


async def test_tail_numeric_first_arg_treated_as_n(cog, gctx, tmp_path):
    _error_log(tmp_path, [_log_line('ERROR', 'err')])
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        await cog.devlog_tail.callback(cog, gctx, level='10', n=50)
    # Should succeed (level defaulted to 'error', n=10)
    gctx.send.assert_awaited_once()
