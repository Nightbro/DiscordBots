"""
Per-guild settings helpers.

Per-guild values override the global defaults from config.yaml.
If a guild has no override for a key, the global default is returned.

Stored in data/guild_config.json:
{
    "guild_id": {
        "auto_join": true,
        "auto_leave": false
    },
    ...
}
"""

from __future__ import annotations

from typing import Any

from utils.config import AUTO_JOIN, AUTO_LEAVE
from utils.persistence import GuildConfig

_DEFAULT_LOCALE = 'en'

# Map setting key → global default value
_DEFAULTS: dict[str, Any] = {
    'auto_join': AUTO_JOIN,
    'auto_leave': AUTO_LEAVE,
    'locale': _DEFAULT_LOCALE,
}


def get_setting(guild_id: int, key: str) -> Any:
    """Return the per-guild value for key, falling back to the global default."""
    cfg = GuildConfig()
    guild_settings: dict = cfg.get(str(guild_id), {})
    return guild_settings.get(key, _DEFAULTS[key])


def set_setting(guild_id: int, key: str, value: Any) -> None:
    """Set a per-guild override for key."""
    cfg = GuildConfig()
    settings: dict = cfg.get(str(guild_id), {})
    settings[key] = value
    cfg.set(str(guild_id), settings)


def reset_setting(guild_id: int, key: str) -> None:
    """Remove a per-guild override so the global default takes effect again."""
    cfg = GuildConfig()
    settings: dict = cfg.get(str(guild_id), {})
    settings.pop(key, None)
    cfg.set(str(guild_id), settings)


def get_all_settings(guild_id: int) -> dict[str, Any]:
    """Return all effective settings for a guild (per-guild overrides + global defaults)."""
    cfg = GuildConfig()
    overrides: dict = cfg.get(str(guild_id), {})
    return {key: overrides.get(key, default) for key, default in _DEFAULTS.items()}


def get_auto_join(guild_id: int) -> bool:
    return bool(get_setting(guild_id, 'auto_join'))


def get_auto_leave(guild_id: int) -> bool:
    return bool(get_setting(guild_id, 'auto_leave'))


def get_locale(guild_id: int) -> str:
    return str(get_setting(guild_id, 'locale'))


def set_locale(guild_id: int, locale: str) -> None:
    set_setting(guild_id, 'locale', locale)
