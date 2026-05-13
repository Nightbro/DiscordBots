import json
from pathlib import Path

from utils.config import SOUNDBOARD_CONFIG_FILE


def load_soundboard_config() -> dict:
    if SOUNDBOARD_CONFIG_FILE.exists():
        return json.loads(SOUNDBOARD_CONFIG_FILE.read_text(encoding='utf-8'))
    return {}


def save_soundboard_config(config: dict):
    SOUNDBOARD_CONFIG_FILE.write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8'
    )


def get_sounds(guild_id: int) -> dict:
    """Return all sounds for a guild as {name: entry}."""
    config = load_soundboard_config()
    return config.get(str(guild_id), {})


def get_sound(guild_id: int, name: str) -> dict | None:
    """Return the entry for a single sound, or None if not found."""
    return get_sounds(guild_id).get(name)


def add_sound(guild_id: int, name: str, emoji: str, file_path: str, source: str):
    config = load_soundboard_config()
    config.setdefault(str(guild_id), {})[name] = {
        'emoji': emoji,
        'file': file_path,
        'source': source,
    }
    save_soundboard_config(config)


def remove_sound(guild_id: int, name: str) -> dict | None:
    """Remove and return the entry, or None if not found."""
    config = load_soundboard_config()
    gid = str(guild_id)
    entry = config.get(gid, {}).pop(name, None)
    if entry is not None:
        save_soundboard_config(config)
    return entry
