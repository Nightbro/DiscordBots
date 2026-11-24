import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils import devlog
from utils.devlog import DevlogHandler, GuildContextFilter, format_entry, targets_for


@pytest.fixture(autouse=True)
def devlog_file(tmp_path):
    with patch('utils.config.DEVLOG_CONFIG_FILE', tmp_path / 'devlog_config.json'):
        yield


def _record(msg='boom', level=logging.WARNING, guild_id=None, name='utils.voice', exc_info=None):
    rec = logging.LogRecord(name, level, __file__, 1, msg, None, exc_info)
    if guild_id is not None:
        rec.guild_id = guild_id
    return rec


# ---------------------------------------------------------------------------
# Settings + routing
# ---------------------------------------------------------------------------

def test_targets_empty_by_default():
    assert targets_for(1) == []
    assert targets_for(None) == []


def test_guild_record_goes_only_to_its_guild():
    devlog.set_guild_target(1, 'channel', 100)
    devlog.set_guild_target(2, 'channel', 200)
    assert targets_for(1) == [('channel', 100)]
    assert targets_for(2) == [('channel', 200)]
    assert targets_for(3) == []


def test_unscoped_record_goes_only_to_all_flagged_targets():
    devlog.set_guild_target(1, 'channel', 100)
    devlog.set_guild_target(2, 'dm', 42, include_all=True)
    assert targets_for(None) == [('dm', 42)]


def test_owner_dm_receives_everything_without_duplicates():
    devlog.set_guild_target(1, 'dm', 42)
    devlog.set_owner_dm(42)
    assert targets_for(1) == [('dm', 42)]
    assert targets_for(9) == [('dm', 42)]
    assert targets_for(None) == [('dm', 42)]


def test_clear_guild_target():
    devlog.set_guild_target(1, 'channel', 100)
    assert devlog.clear_guild_target(1) is True
    assert devlog.clear_guild_target(1) is False
    assert devlog.get_guild_target(1) is None


def test_set_owner_dm_none_turns_it_off():
    devlog.set_owner_dm(42)
    devlog.set_owner_dm(None)
    assert devlog.get_owner_dm() is None
    assert targets_for(None) == []


# ---------------------------------------------------------------------------
# Guild tagging + formatting
# ---------------------------------------------------------------------------

def test_filter_uses_context_var():
    token = devlog.current_guild.set(77)
    try:
        rec = _record()
        GuildContextFilter().filter(rec)
    finally:
        devlog.current_guild.reset(token)
    assert rec.guild_id == 77


def test_filter_keeps_explicit_guild_id():
    token = devlog.current_guild.set(77)
    try:
        rec = _record(guild_id=5)
        GuildContextFilter().filter(rec)
    finally:
        devlog.current_guild.reset(token)
    assert rec.guild_id == 5


def test_format_entry_includes_level_guild_message_and_traceback():
    try:
        raise ValueError('bad file')
    except ValueError:
        import sys
        rec = _record('download failed', level=logging.ERROR, guild_id=5, exc_info=sys.exc_info())
    text = format_entry(rec)
    assert '[ERROR]' in text
    assert 'guild 5' in text
    assert 'download failed' in text
    assert 'ValueError: bad file' in text


def test_format_entry_without_guild():
    rec = _record()
    rec.guild_id = None
    assert 'no server' in format_entry(rec)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def _bot_with_channel():
    channel = MagicMock()
    channel.send = AsyncMock()
    user = MagicMock()
    user.send = AsyncMock()
    bot = MagicMock()
    bot.get_channel.return_value = channel
    bot.get_user.return_value = user
    return bot, channel, user


async def test_handler_sends_guild_records_to_that_guilds_channel():
    devlog.set_guild_target(1, 'channel', 100)
    bot, channel, _ = _bot_with_channel()
    h = DevlogHandler()
    h._bot = bot
    h.handle(_record('guild one broke', guild_id=1))
    h.handle(_record('guild two broke', guild_id=2))
    await h.flush_pending()
    bot.get_channel.assert_called_once_with(100)
    embed = channel.send.await_args.kwargs['embed']
    assert 'guild one broke' in embed.description
    assert 'guild two broke' not in embed.description


async def test_handler_batches_and_counts_overflow():
    devlog.set_owner_dm(42)
    bot, _, user = _bot_with_channel()
    h = DevlogHandler()
    h._bot = bot
    for i in range(devlog.MAX_ENTRIES + 3):
        h.handle(_record(f'err {i}', guild_id=1))
    await h.flush_pending()
    user.send.assert_awaited_once()
    assert '3 more' in user.send.await_args.kwargs['embed'].description


async def test_handler_ignores_records_below_warning():
    devlog.set_owner_dm(42)
    h = DevlogHandler()
    logger = logging.getLogger('test_devlog_levels')
    logger.addHandler(h)
    try:
        logger.info('fine')
        logger.warning('not fine')
    finally:
        logger.removeHandler(h)
    assert [r.getMessage() for r in h._pending] == ['not fine']


async def test_handler_ignores_its_own_records():
    devlog.set_owner_dm(42)
    h = DevlogHandler()
    h.handle(_record(name='utils.devlog'))
    assert not h._pending


async def test_handler_send_failure_is_swallowed():
    devlog.set_guild_target(1, 'channel', 100)
    bot, channel, _ = _bot_with_channel()
    channel.send.side_effect = RuntimeError('missing access')
    h = DevlogHandler()
    h._bot = bot
    h.handle(_record(guild_id=1))
    await h.flush_pending()  # must not raise


async def test_handler_fetches_uncached_destinations():
    devlog.set_guild_target(1, 'dm', 42)
    bot, _, user = _bot_with_channel()
    bot.get_user.return_value = None
    bot.fetch_user = AsyncMock(return_value=user)
    h = DevlogHandler()
    h._bot = bot
    h.handle(_record(guild_id=1))
    await h.flush_pending()
    bot.fetch_user.assert_awaited_once_with(42)
    user.send.assert_awaited_once()


async def test_handler_start_sends_records_logged_before_start():
    devlog.set_owner_dm(42)
    bot, _, user = _bot_with_channel()
    h = DevlogHandler()
    h.handle(_record('startup failure'))
    with patch('utils.devlog.BATCH_WINDOW', 0):
        h.start(bot)
        for _ in range(20):
            await asyncio.sleep(0)
            if user.send.await_count:
                break
    h._task.cancel()
    assert 'startup failure' in user.send.await_args.kwargs['embed'].description


async def test_handler_emit_from_other_thread_wakes_sender():
    import threading
    devlog.set_owner_dm(42)
    bot, _, user = _bot_with_channel()
    h = DevlogHandler()
    with patch('utils.devlog.BATCH_WINDOW', 0):
        h.start(bot)
        t = threading.Thread(target=h.handle, args=(_record('from player thread', guild_id=1),))
        t.start()
        t.join()
        for _ in range(50):
            await asyncio.sleep(0.01)
            if user.send.await_count:
                break
    h._task.cancel()
    assert 'from player thread' in user.send.await_args.kwargs['embed'].description


# ---------------------------------------------------------------------------
# tail_log
# ---------------------------------------------------------------------------

_TS = '2024-01-15 12:00:00'

def _log_line(level: str, msg: str) -> str:
    pad = level.ljust(8)
    return f'{_TS} [{pad}] utils.test: {msg}'


def _write_log(path, lines: list[str]) -> None:
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def test_tail_log_no_files_returns_empty(tmp_path):
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        records, f = devlog.tail_log()
    assert records == []
    assert f is None


def test_tail_log_reads_errors_log_for_error_level(tmp_path):
    errors_log = tmp_path / 'errors_20240115_120000.log'
    _write_log(errors_log, [
        _log_line('ERROR', 'something failed'),
        _log_line('WARNING', 'just a warning'),
    ])
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        records, f = devlog.tail_log('error')
    assert f == errors_log
    assert len(records) == 1
    assert 'something failed' in records[0]


def test_tail_log_warning_includes_warnings(tmp_path):
    errors_log = tmp_path / 'errors_20240115_120000.log'
    _write_log(errors_log, [
        _log_line('ERROR', 'err'),
        _log_line('WARNING', 'warn'),
        _log_line('CRITICAL', 'crit'),
    ])
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        records, _ = devlog.tail_log('warning')
    assert len(records) == 3


def test_tail_log_critical_only(tmp_path):
    errors_log = tmp_path / 'errors_20240115_120000.log'
    _write_log(errors_log, [
        _log_line('ERROR', 'err'),
        _log_line('CRITICAL', 'crit'),
    ])
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        records, _ = devlog.tail_log('critical')
    assert len(records) == 1
    assert 'crit' in records[0]


def test_tail_log_caps_to_n(tmp_path):
    errors_log = tmp_path / 'errors_20240115_120000.log'
    lines = [_log_line('ERROR', f'err {i}') for i in range(10)]
    _write_log(errors_log, lines)
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        records, _ = devlog.tail_log('error', n=3)
    assert len(records) == 3
    assert 'err 9' in records[-1]


def test_tail_log_includes_traceback_continuation(tmp_path):
    errors_log = tmp_path / 'errors_20240115_120000.log'
    _write_log(errors_log, [
        _log_line('ERROR', 'crash'),
        'Traceback (most recent call last):',
        '  File "foo.py", line 1',
        'ValueError: bad',
    ])
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        records, _ = devlog.tail_log('error')
    assert len(records) == 1
    assert 'ValueError' in records[0]


def test_tail_log_all_uses_full_log(tmp_path):
    full_log = tmp_path / 'echo_20240115_120000.log'
    _write_log(full_log, [
        _log_line('DEBUG', 'debug msg'),
        _log_line('INFO', 'info msg'),
    ])
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        records, f = devlog.tail_log('all')
    assert f == full_log
    assert len(records) == 2


def test_tail_log_empty_matching(tmp_path):
    errors_log = tmp_path / 'errors_20240115_120000.log'
    _write_log(errors_log, [_log_line('WARNING', 'just a warn')])
    with patch('utils.config.LOGS_DIR', tmp_path), \
         patch('utils.config.BOT_NAME', 'echo'):
        records, f = devlog.tail_log('critical')
    assert records == []
    assert f == errors_log  # file exists, just no matching records
