"""
Intro configuration helpers.

All state is stored in data/intro_config.json via IntroConfig (persistence.py).

Schema per user entry (keyed by str(user_id)):
{
    "default": "filename.mp3",          # played when no schedule matches
    "schedule": {
        "mon": "weekday.mp3",
        "fri": "friday.mp3"
    },
    "overrides": {                       # YYYY-MM-DD → filename
        "2024-12-25": "xmas.mp3"
    },
    "auto_join": false                   # bot auto-joins user's channel on guild join
}
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

from utils.config import INTRO_SOUNDS_DIR
from utils.persistence import IntroConfig

_DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
_DAY_ALIASES: dict[str, str] = {
    'monday': 'mon', 'tuesday': 'tue', 'wednesday': 'wed', 'thursday': 'thu',
    'friday': 'fri', 'saturday': 'sat', 'sunday': 'sun',
    **{d: d for d in _DAYS},
}


def parse_days(text: str) -> list[str]:
    """Parse comma-separated day names/abbreviations into canonical 3-letter codes."""
    result = []
    for part in text.split(','):
        key = part.strip().lower()
        if key in _DAY_ALIASES:
            result.append(_DAY_ALIASES[key])
    return result


def canonicalize_days(days: list[str]) -> list[str]:
    """Return days sorted in week order (mon→sun), deduped."""
    seen = set()
    out = []
    for d in _DAYS:
        if d in days and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def user_dir(user_id: int) -> Path:
    """Return the per-user intro sounds directory, creating it if needed."""
    d = INTRO_SOUNDS_DIR / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_user_entry(user_id: int) -> dict:
    cfg = IntroConfig()
    return cfg.get(str(user_id), {})


def _save_user_entry(user_id: int, entry: dict) -> None:
    cfg = IntroConfig()
    cfg.set(str(user_id), entry)


def set_default_entry(user_id: int, filename: str) -> None:
    entry = get_user_entry(user_id)
    entry['default'] = filename
    _save_user_entry(user_id, entry)


def set_schedule_entry(user_id: int, days: list[str], filename: str) -> None:
    entry = get_user_entry(user_id)
    schedule: dict[str, str] = entry.get('schedule', {})
    for day in days:
        schedule[day] = filename
    entry['schedule'] = schedule
    _save_user_entry(user_id, entry)


def remove_schedule_entry(user_id: int, days: list[str]) -> list[str]:
    """Remove schedule entries for the given days. Returns days actually removed."""
    entry = get_user_entry(user_id)
    schedule: dict[str, str] = entry.get('schedule', {})
    removed = []
    for day in days:
        if day in schedule:
            del schedule[day]
            removed.append(day)
    entry['schedule'] = schedule
    _save_user_entry(user_id, entry)
    return removed


def set_override_entry(user_id: int, date_str: str, filename: str) -> None:
    """Set a YYYY-MM-DD date override."""
    entry = get_user_entry(user_id)
    overrides: dict[str, str] = entry.get('overrides', {})
    overrides[date_str] = filename
    entry['overrides'] = overrides
    _save_user_entry(user_id, entry)


def remove_override_entry(user_id: int, date_str: str) -> bool:
    entry = get_user_entry(user_id)
    overrides: dict[str, str] = entry.get('overrides', {})
    if date_str in overrides:
        del overrides[date_str]
        entry['overrides'] = overrides
        _save_user_entry(user_id, entry)
        return True
    return False


def clear_trigger(user_id: int) -> bool:
    """Remove all intro config for a user. Returns True if anything was cleared."""
    cfg = IntroConfig()
    return cfg.delete(str(user_id))


def get_intro_file(user_id: int, today: Optional[datetime.date] = None) -> Optional[Path]:
    """
    Return the Path to the correct intro file for today, or None if unset.

    Priority: date override → weekday schedule → default.
    """
    entry = get_user_entry(user_id)
    if not entry:
        return None

    if today is None:
        today = datetime.date.today()

    date_str = today.strftime('%Y-%m-%d')
    day_key = _DAYS[today.weekday()]

    filename: Optional[str] = None

    overrides = entry.get('overrides', {})
    if date_str in overrides:
        filename = overrides[date_str]
    elif day_key in entry.get('schedule', {}):
        filename = entry['schedule'][day_key]
    else:
        filename = entry.get('default')

    if not filename:
        return None

    path = user_dir(user_id) / filename
    return path if path.exists() else None


def get_user_intro(user_id: int) -> Optional[Path]:
    """Convenience wrapper using today's date."""
    return get_intro_file(user_id)


def get_auto_join(user_id: int) -> bool:
    return bool(get_user_entry(user_id).get('auto_join', False))


def set_auto_join(user_id: int, value: bool) -> None:
    entry = get_user_entry(user_id)
    entry['auto_join'] = value
    _save_user_entry(user_id, entry)


def list_entries() -> dict[str, dict]:
    """Return all user entries from the config."""
    return IntroConfig().all()
