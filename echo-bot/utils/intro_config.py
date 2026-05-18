"""
Intro configuration helpers — guild-scoped.

Schema (data/intro_config.json), keyed by str(guild_id):
{
  "guild_id": {
    "bot": {
      "default": {"file": "/abs/path.mp3", "source": "human label"},
      "schedule": [{"days": "MON,FRI", "file": "/abs/path.mp3", "source": "label"}]
    },
    "user": { ... },
    "user_<member_id>": {
      "default": {...},
      "schedule": [...],
      "member_name": "DisplayName"
    }
  }
}

Trigger keys: "bot", "user", "user_<member_id>"
Day patterns:  MON  SAT,SUN  MON-FRI  WEEKDAY  WEEKEND  * (any)
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from utils.persistence import IntroConfig

log = logging.getLogger(__name__)

_DAY_NAMES   = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6}
_DAY_ABBREVS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
_ALIASES: dict[str, frozenset] = {
    'WEEKDAY': frozenset(range(5)),
    'WEEKEND': frozenset({5, 6}),
}


def parse_days(pattern: str) -> frozenset:
    """Parse a day pattern into a frozenset of weekday ints (0=Mon … 6=Sun).

    Supports: MON  SAT,SUN  MON-FRI  WEEKDAY  WEEKEND  * (any day).
    Raises ValueError for unrecognised input.
    """
    p = pattern.strip().upper()
    if p == '*':
        return frozenset(range(7))
    if p in _ALIASES:
        return _ALIASES[p]
    days: set[int] = set()
    for token in p.split(','):
        token = token.strip()
        if not token:
            continue
        if '-' in token:
            lo, _, hi = token.partition('-')
            if lo not in _DAY_NAMES or hi not in _DAY_NAMES:
                raise ValueError(f'Invalid day range: {token!r}. Use names like MON-FRI.')
            start, end = _DAY_NAMES[lo], _DAY_NAMES[hi]
            if start > end:
                raise ValueError(
                    f'Day range must go low→high (e.g. MON-FRI, not FRI-MON): {token!r}'
                )
            days.update(range(start, end + 1))
        elif token in _DAY_NAMES:
            days.add(_DAY_NAMES[token])
        else:
            raise ValueError(
                f'Unknown day: {token!r}. Use MON/TUE/WED/THU/FRI/SAT/SUN, '
                f'a range like MON-FRI, or WEEKDAY/WEEKEND.'
            )
    if not days:
        raise ValueError(f'Empty day pattern: {pattern!r}')
    return frozenset(days)


def canonicalize_days(days: frozenset) -> str:
    """Return sorted comma-joined day abbreviations, e.g. frozenset({0,4}) → 'MON,FRI'."""
    return ','.join(_DAY_ABBREVS[d] for d in sorted(days))


# ---------------------------------------------------------------------------
# Internal I/O
# ---------------------------------------------------------------------------

def _load() -> dict:
    return IntroConfig().load()


def _save(data: dict) -> None:
    IntroConfig().save(data)


def _file_for_today(entry: dict) -> Path | None:
    """Return the best file for today from a structured entry dict."""
    today = date.today().weekday()
    for sched in entry.get('schedule', []):
        try:
            days = parse_days(sched['days'])
        except (ValueError, KeyError):
            continue
        if today in days:
            p = Path(sched['file'])
            if p.exists():
                return p

    default = entry.get('default')
    if default:
        p = Path(default['file'])
        if p.exists():
            return p

    return None


def _delete_entry_files(entry: dict) -> None:
    """Delete all audio files referenced by an entry."""
    if default := entry.get('default'):
        Path(default['file']).unlink(missing_ok=True)
    for sched in entry.get('schedule', []):
        Path(sched['file']).unlink(missing_ok=True)


def _ensure_entry(guild_cfg: dict, trigger_key: str) -> dict:
    entry = guild_cfg.get(trigger_key)
    if entry is None:
        entry = {}
        guild_cfg[trigger_key] = entry
    return entry


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_intro_file(guild_id: int, trigger_key: str) -> Path | None:
    """Return the configured intro file for (guild, trigger) for today, or None."""
    data = _load()
    entry = data.get(str(guild_id), {}).get(trigger_key)
    if entry:
        return _file_for_today(entry)
    return None


def get_user_intro(guild_id: int, member_id: int) -> Path | None:
    """Return the best intro for a member joining voice.

    Priority: per-member entry → server-wide 'user' entry.
    """
    data = _load()
    guild_cfg = data.get(str(guild_id), {})
    for key in (f'user_{member_id}', 'user'):
        entry = guild_cfg.get(key)
        if entry:
            p = _file_for_today(entry)
            if p:
                return p
    return None


def list_entries(guild_id: int) -> dict:
    """Return all trigger entries for a guild (dict keyed by trigger key)."""
    data = _load()
    return {k: v for k, v in data.get(str(guild_id), {}).items()}


def set_default_entry(
    guild_id: int,
    trigger_key: str,
    file_path: str,
    source: str,
    member_name: str | None = None,
) -> None:
    """Set the default intro for a trigger, preserving any existing schedule."""
    data = _load()
    guild_cfg = data.setdefault(str(guild_id), {})
    entry = _ensure_entry(guild_cfg, trigger_key)
    entry['default'] = {'file': file_path, 'source': source}
    if member_name is not None:
        entry['member_name'] = member_name
    _save(data)


def set_schedule_entry(
    guild_id: int, trigger_key: str, days_str: str, file_path: str, source: str
) -> str:
    """Add or replace a day-specific override. Returns the canonical days string."""
    days = parse_days(days_str)
    canon = canonicalize_days(days)

    data = _load()
    guild_cfg = data.setdefault(str(guild_id), {})
    entry = _ensure_entry(guild_cfg, trigger_key)
    schedule = entry.setdefault('schedule', [])

    for i, item in enumerate(schedule):
        if item.get('days') == canon:
            Path(item['file']).unlink(missing_ok=True)
            schedule[i] = {'days': canon, 'file': file_path, 'source': source}
            break
    else:
        schedule.append({'days': canon, 'file': file_path, 'source': source})

    _save(data)
    return canon


def remove_schedule_entry(guild_id: int, trigger_key: str, days_str: str) -> bool:
    """Remove a day-specific override. Returns True if found and removed."""
    days = parse_days(days_str)
    canon = canonicalize_days(days)

    data = _load()
    guild_cfg = data.get(str(guild_id), {})
    entry = guild_cfg.get(trigger_key, {})
    schedule = entry.get('schedule', [])

    new_schedule = []
    removed = False
    for item in schedule:
        if item.get('days') == canon:
            Path(item['file']).unlink(missing_ok=True)
            removed = True
        else:
            new_schedule.append(item)

    if not removed:
        return False

    entry['schedule'] = new_schedule
    guild_cfg[trigger_key] = entry
    _save(data)
    return True


def clear_trigger(guild_id: int, trigger_key: str) -> dict | None:
    """Remove a trigger entry entirely (deletes audio files). Returns removed entry or None."""
    data = _load()
    entry = data.get(str(guild_id), {}).pop(trigger_key, None)
    if entry is not None:
        _delete_entry_files(entry)
        _save(data)
    return entry


def rename_entry(guild_id: int, trigger_key: str, name: str) -> bool:
    """Update the source label of a trigger's default entry. Returns True if updated."""
    data = _load()
    entry = data.get(str(guild_id), {}).get(trigger_key)
    if not entry or 'default' not in entry:
        return False
    entry['default']['source'] = name
    _save(data)
    return True
