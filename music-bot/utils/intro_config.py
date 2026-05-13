import json
import logging
from pathlib import Path

from .config import INTRO_CONFIG_FILE, _INTRO_FILE

log = logging.getLogger('music-bot.intro_config')


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
        p = Path(entry['file'])
        if p.exists():
            return p
    if trigger in ('bot', 'user') and _INTRO_FILE.exists():
        return _INTRO_FILE
    return None


def get_user_intro(guild_id: int, member_id: int) -> Path | None:
    """Return the best intro for a member joining voice.

    Priority: per-member intro → server-wide user intro → .env default.
    """
    config = load_intro_config()
    guild_cfg = config.get(str(guild_id), {})

    for key in (f'user_{member_id}', 'user'):
        entry = guild_cfg.get(key)
        if entry:
            p = Path(entry['file'])
            if p.exists():
                return p

    if _INTRO_FILE.exists():
        return _INTRO_FILE
    return None
