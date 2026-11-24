"""
Dev log: forward WARNING+ log records to Discord (a channel or a DM).

Each server opts in separately (`!devlog`), and only receives errors that
happened in that server. Records not tied to any server (startup, gateway,
cog loading) go only to destinations flagged ``all`` and to the owner's DM
subscription, so one server's details never leak into another's channel.

Stored in data/devlog_config.json:
{
    "guilds": {
        "<guild_id>": {"kind": "channel" | "dm", "id": <channel or user id>, "all": false}
    },
    "owner_dm": <user id> | null      # receives every record from every server
}

Which server a record belongs to comes from `current_guild` (a ContextVar set
per event/command in bot.py and per playback step in VoiceStreamer), or from
``extra={'guild_id': ...}`` for code running outside the event loop.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import re
import threading
import traceback
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from utils.persistence import DevlogConfig

if TYPE_CHECKING:
    import discord
    from discord.ext import commands

log = logging.getLogger(__name__)

current_guild: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    'devlog_current_guild', default=None
)

# Wait this long after the first record so bursts go out as one message.
BATCH_WINDOW = 3.0
# Entries shown per message; the rest are counted as "…and N more".
MAX_ENTRIES = 5
# Records kept while waiting to send (oldest dropped first).
MAX_PENDING = 200
_TRACEBACK_CHARS = 900

Target = tuple[str, int]  # ('channel' | 'dm', id)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_guild_target(guild_id: int) -> dict | None:
    return DevlogConfig().get('guilds', {}).get(str(guild_id))


def set_guild_target(guild_id: int, kind: str, target_id: int, include_all: bool = False) -> None:
    cfg = DevlogConfig()
    guilds: dict = cfg.get('guilds', {})
    guilds[str(guild_id)] = {'kind': kind, 'id': target_id, 'all': include_all}
    cfg.set('guilds', guilds)


def clear_guild_target(guild_id: int) -> bool:
    """Turn dev log off for a guild. Returns True if it was on."""
    cfg = DevlogConfig()
    guilds: dict = cfg.get('guilds', {})
    existed = guilds.pop(str(guild_id), None) is not None
    cfg.set('guilds', guilds)
    return existed


def get_owner_dm() -> int | None:
    return DevlogConfig().get('owner_dm')


def set_owner_dm(user_id: int | None) -> None:
    DevlogConfig().set('owner_dm', user_id)


def targets_for(guild_id: int | None) -> list[Target]:
    """Destinations for a record from guild_id (None = not tied to a server)."""
    data = DevlogConfig().all()
    guilds: dict = data.get('guilds', {})
    found: list[Target] = []
    if guild_id is not None:
        entry = guilds.get(str(guild_id))
        if entry:
            found.append((entry['kind'], int(entry['id'])))
    else:
        found.extend((e['kind'], int(e['id'])) for e in guilds.values() if e.get('all'))
    owner = data.get('owner_dm')
    if owner:
        found.append(('dm', int(owner)))
    return list(dict.fromkeys(found))


# ---------------------------------------------------------------------------
# Logging plumbing
# ---------------------------------------------------------------------------

class GuildContextFilter(logging.Filter):
    """Stamp each record with the guild it happened in (record.guild_id)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, 'guild_id', None) is None:
            record.guild_id = current_guild.get()
        return True


def format_entry(record: logging.LogRecord) -> str:
    where = f'guild {record.guild_id}' if getattr(record, 'guild_id', None) else 'no server'
    text = f'[{record.levelname}] {record.name} ({where})\n{record.getMessage()}'
    if record.exc_info and record.exc_info[1] is not None:
        tb = ''.join(traceback.format_exception(*record.exc_info))
        if len(tb) > _TRACEBACK_CHARS:
            tb = '…' + tb[-_TRACEBACK_CHARS:]
        text += '\n' + tb.rstrip()
    return text


class DevlogHandler(logging.Handler):
    """Queues WARNING+ records and sends them to Discord in rate-limited batches.

    emit() may run on any thread (FFmpeg player threads log too), so it only
    appends to a locked deque and wakes the sender on the event loop.
    Records logged before start() are kept and sent once the bot is ready.
    """

    def __init__(self, level: int = logging.WARNING) -> None:
        super().__init__(level)
        self.addFilter(GuildContextFilter())
        self._pending: deque[logging.LogRecord] = deque(maxlen=MAX_PENDING)
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None
        self._task: asyncio.Task | None = None
        self._bot: commands.Bot | None = None

    # -- producer side (any thread) ------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        # Never forward our own send failures — that would loop.
        if record.name == __name__:
            return
        with self._lock:
            self._pending.append(record)
        loop, wake = self._loop, self._wake
        if loop is not None and wake is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(wake.set)
            except RuntimeError:
                pass  # loop shutting down

    # -- consumer side (event loop) -----------------------------------

    def start(self, bot: commands.Bot) -> None:
        """Begin sending. Call from the running event loop (e.g. on_ready)."""
        if self._task and not self._task.done():
            return
        self._bot = bot
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self._task = self._loop.create_task(self._run(), name='devlog-sender')
        with self._lock:
            if self._pending:
                self._wake.set()

    async def _run(self) -> None:
        assert self._wake is not None
        while True:
            await self._wake.wait()
            await asyncio.sleep(BATCH_WINDOW)
            self._wake.clear()
            try:
                await self.flush_pending()
            except Exception:
                log.exception('Dev log: sending batch failed')

    async def flush_pending(self) -> None:
        with self._lock:
            records = list(self._pending)
            self._pending.clear()
        if not records:
            return
        batches: dict[Target, list[logging.LogRecord]] = {}
        for record in records:
            for target in targets_for(getattr(record, 'guild_id', None)):
                batches.setdefault(target, []).append(record)
        for target, recs in batches.items():
            entries = [format_entry(r) for r in recs[:MAX_ENTRIES]]
            await self._send(target, entries, len(recs) - len(entries))

    async def _send(self, target: Target, entries: list[str], suppressed: int) -> None:
        from utils.message import MessageWriter
        bot = self._bot
        if bot is None:
            return
        kind, target_id = target
        try:
            dest: discord.abc.Messageable | None
            if kind == 'dm':
                dest = bot.get_user(target_id) or await bot.fetch_user(target_id)
            else:
                dest = bot.get_channel(target_id) or await bot.fetch_channel(target_id)
            await dest.send(embed=MessageWriter.devlog(entries, suppressed))
        except Exception as exc:
            log.warning('Dev log: could not send to %s %s: %s', kind, target_id, exc)


handler = DevlogHandler()


# ---------------------------------------------------------------------------
# Log file tail
# ---------------------------------------------------------------------------

_LOG_HEADER_RE = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[')

# Maps level keyword → set of level names that satisfy "at or above this level".
_LEVEL_FILTER: dict[str, frozenset[str]] = {
    'critical': frozenset({'CRITICAL'}),
    'error':    frozenset({'ERROR', 'CRITICAL'}),
    'warning':  frozenset({'WARNING', 'ERROR', 'CRITICAL'}),
    'warn':     frozenset({'WARNING', 'ERROR', 'CRITICAL'}),
    'info':     frozenset({'INFO', 'WARNING', 'ERROR', 'CRITICAL'}),
    'debug':    frozenset({'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}),
    'all':      frozenset({'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}),
}

VALID_LEVELS: frozenset[str] = frozenset(_LEVEL_FILTER)


def tail_log(level: str = 'error', n: int = 50) -> tuple[list[str], Path | None]:
    """Return the last *n* log records at or above *level*.

    Uses the errors-only log for WARNING/ERROR/CRITICAL (smaller, faster);
    falls back to the full debug log for INFO/DEBUG/all.

    Returns ``(records, source_file)``.  ``records`` is empty when nothing
    matches or the log directory has no files; ``source_file`` is ``None``
    when no log file was found at all.
    """
    from utils.config import LOGS_DIR, BOT_NAME

    levels = _LEVEL_FILTER.get(level.lower(), _LEVEL_FILTER['error'])
    # Errors-only log has WARNING+ — sufficient for warning/error/critical.
    errors_only = levels <= frozenset({'WARNING', 'ERROR', 'CRITICAL'})
    prefix = 'errors_' if errors_only else f'{BOT_NAME.lower()}_'

    files = sorted(LOGS_DIR.glob(f'{prefix}*.log'), key=lambda p: p.stat().st_mtime)
    if not files:
        return [], None

    log_file = files[-1]
    try:
        text = log_file.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return [], None

    # Group lines into records; each record starts with a timestamp header.
    records: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if _LOG_HEADER_RE.match(line):
            if current:
                records.append('\n'.join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        records.append('\n'.join(current))

    filtered = [r for r in records if _record_matches(r, levels)]
    return filtered[-n:], log_file


def _record_matches(record: str, levels: frozenset[str]) -> bool:
    # Level appears in the header line, e.g. "... [ERROR   ] ..."
    header = record.split('\n', 1)[0]
    return any(f'[{lvl}' in header for lvl in levels)
