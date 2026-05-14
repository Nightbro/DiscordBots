import json
import logging
from datetime import date
from pathlib import Path

from .config import INTRO_CONFIG_FILE, _INTRO_FILE

log = logging.getLogger('music-bot.intro_config')

_DAY_NAMES   = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6}
_DAY_ABBREVS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
_ALIASES     = {'WEEKDAY': frozenset(range(5)), 'WEEKEND': frozenset({5, 6})}


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
    days: set = set()
    for token in p.split(','):
        token = token.strip()
        if not token:
            continue
        if '-' in token:
            lo, _, hi = token.partition('-')
            if lo not in _DAY_NAMES or hi not in _DAY_NAMES:
                raise ValueError(
                    f'Invalid day range: {token!r}. Use names like MON-FRI.'
                )
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


def _file_for_today(entry: dict) -> Path | None:
    """Return the best file for today from an entry dict, or None if unavailable.

    Handles old flat format {file, source, ...} and new structured format
    {default: {...}, schedule: [...], ...}.  Schedule entries are checked first
    (first match wins); falls back to default.
    """
    if 'file' in entry:  # old flat format — treat as default
        p = Path(entry['file'])
        return p if p.exists() else None

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


def _delete_entry_files(entry: dict):
    """Delete all audio files referenced by an entry (handles both formats)."""
    if 'file' in entry:
        Path(entry['file']).unlink(missing_ok=True)
        return
    if default := entry.get('default'):
        Path(default['file']).unlink(missing_ok=True)
    for sched in entry.get('schedule', []):
        Path(sched['file']).unlink(missing_ok=True)


def _ensure_structured(guild_cfg: dict, trigger_key: str) -> dict:
    """Return a new-format entry dict for trigger_key, migrating flat format if needed."""
    entry = guild_cfg.get(trigger_key)
    if entry is None:
        entry = {}
        guild_cfg[trigger_key] = entry
        return entry
    if 'file' in entry:
        new_entry: dict = {'default': {'file': entry['file'], 'source': entry.get('source', '')}}
        if 'member_name' in entry:
            new_entry['member_name'] = entry['member_name']
        guild_cfg[trigger_key] = new_entry
        return new_entry
    return entry


def load_intro_config() -> dict:
    if INTRO_CONFIG_FILE.exists():
        return json.loads(INTRO_CONFIG_FILE.read_text(encoding='utf-8'))
    return {}


def save_intro_config(data: dict):
    INTRO_CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def get_intro_file(guild_id: int, trigger: str) -> Path | None:
    """Return the configured intro MP3 for (guild, trigger), falling back to the .env default.

    trigger is 'bot', 'user', or 'user_<member_id>'.
    The .env fallback only applies to 'bot' and 'user' (not per-member keys).
    """
    config = load_intro_config()
    entry = config.get(str(guild_id), {}).get(trigger)
    if entry:
        p = _file_for_today(entry)
        if p:
            return p
    if trigger in ('bot', 'user') and _INTRO_FILE.exists():
        return _INTRO_FILE
    return None


def get_auto_join(guild_id: int) -> bool:
    config = load_intro_config()
    return bool(config.get(str(guild_id), {}).get('_auto_join', False))


def set_auto_join(guild_id: int, enabled: bool):
    config = load_intro_config()
    config.setdefault(str(guild_id), {})['_auto_join'] = enabled
    save_intro_config(config)


def get_user_intro(guild_id: int, member_id: int) -> Path | None:
    """Return the best intro for a member joining voice.

    Priority: per-member intro → server-wide user intro → .env default.
    """
    config = load_intro_config()
    guild_cfg = config.get(str(guild_id), {})

    for key in (f'user_{member_id}', 'user'):
        entry = guild_cfg.get(key)
        if entry:
            p = _file_for_today(entry)
            if p:
                return p

    if _INTRO_FILE.exists():
        return _INTRO_FILE
    return None


def set_default_entry(
    guild_id: int,
    trigger_key: str,
    file_path: str,
    source: str,
    member_name: str | None = None,
):
    """Set the default intro for a trigger, preserving any existing schedule."""
    config = load_intro_config()
    guild_cfg = config.setdefault(str(guild_id), {})
    entry = _ensure_structured(guild_cfg, trigger_key)
    entry['default'] = {'file': file_path, 'source': source}
    if member_name is not None:
        entry['member_name'] = member_name
    save_intro_config(config)


def set_schedule_entry(
    guild_id: int, trigger_key: str, days_str: str, file_path: str, source: str
) -> str:
    """Add or replace a day-specific override. Returns the canonical days string."""
    days  = parse_days(days_str)
    canon = canonicalize_days(days)

    config    = load_intro_config()
    guild_cfg = config.setdefault(str(guild_id), {})
    entry     = _ensure_structured(guild_cfg, trigger_key)
    schedule  = entry.setdefault('schedule', [])

    for i, item in enumerate(schedule):
        if item.get('days') == canon:
            Path(item['file']).unlink(missing_ok=True)
            schedule[i] = {'days': canon, 'file': file_path, 'source': source}
            break
    else:
        schedule.append({'days': canon, 'file': file_path, 'source': source})

    save_intro_config(config)
    return canon


def remove_schedule_entry(guild_id: int, trigger_key: str, days_str: str) -> bool:
    """Remove a day-specific override. Returns True if found and removed."""
    days  = parse_days(days_str)
    canon = canonicalize_days(days)

    config    = load_intro_config()
    guild_cfg = config.get(str(guild_id), {})
    entry     = guild_cfg.get(trigger_key, {})
    schedule  = entry.get('schedule', [])

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
    save_intro_config(config)
    return True


def clear_trigger(guild_id: int, trigger_key: str) -> dict | None:
    """Remove a trigger entry entirely (default + all schedule overrides).

    Returns the removed entry dict, or None if nothing was configured.
    """
    config = load_intro_config()
    entry  = config.get(str(guild_id), {}).pop(trigger_key, None)
    if entry is not None:
        _delete_entry_files(entry)
        save_intro_config(config)
    return entry
