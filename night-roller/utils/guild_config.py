"""Per-guild dice settings.

Per-guild values override the global defaults from config.yaml. A guild with
no override for a key gets the global default.

Stored in data/guild_config.json:
{
    "guild_id": {
        "system": "wod",
        "die": 10,
        "difficulty": 6,
        "subtract_ones": true
    },
    ...
}
"""

from __future__ import annotations

from typing import Any

from utils.config import (
    DEFAULT_DIE,
    DEFAULT_DIFFICULTY,
    DEFAULT_SUBTRACT_ONES,
    DEFAULT_SYSTEM,
    MAX_DICE,
    MAX_SIDES,
)
from utils.persistence import GuildConfig

# Roll systems. "standard" sums the dice; "wod" counts successes against a
# difficulty and cancels them with 1s.
SYSTEM_STANDARD = 'standard'
SYSTEM_WOD = 'wod'
SYSTEMS = (SYSTEM_STANDARD, SYSTEM_WOD)

# System-specific defaults applied when a guild switches system without having
# set an explicit die of its own.
SYSTEM_DIE = {SYSTEM_STANDARD: DEFAULT_DIE, SYSTEM_WOD: 10}

_DEFAULTS: dict[str, Any] = {
    'system': DEFAULT_SYSTEM,
    'die': DEFAULT_DIE,
    'difficulty': DEFAULT_DIFFICULTY,
    'subtract_ones': DEFAULT_SUBTRACT_ONES,
}


# Embed title used when a !config command rejects a value.
SETTING_ERROR_TITLE = 'Setting not changed'


class SettingError(ValueError):
    """Raised for a rejected setting value — the message is shown to the user."""


def get_setting(guild_id: int, key: str) -> Any:
    """Return the per-guild value for key, falling back to the global default."""
    settings: dict = GuildConfig().get(str(guild_id), {})
    return settings.get(key, _DEFAULTS[key])


def set_setting(guild_id: int, key: str, value: Any) -> None:
    """Set a per-guild override for key."""
    cfg = GuildConfig()
    settings: dict = cfg.get(str(guild_id), {})
    settings[key] = value
    cfg.set(str(guild_id), settings)


def reset_guild(guild_id: int) -> None:
    """Drop every override so the guild falls back to the global defaults."""
    GuildConfig().delete(str(guild_id))


def get_all_settings(guild_id: int) -> dict[str, Any]:
    """Effective settings for a guild — overrides merged over the defaults."""
    overrides: dict = GuildConfig().get(str(guild_id), {})
    return {key: overrides.get(key, default) for key, default in _DEFAULTS.items()}


# --- Typed accessors -------------------------------------------------------

def get_system(guild_id: int) -> str:
    return str(get_setting(guild_id, 'system'))


def get_die(guild_id: int) -> int:
    return int(get_setting(guild_id, 'die'))


def get_difficulty(guild_id: int) -> int:
    return int(get_setting(guild_id, 'difficulty'))


def get_subtract_ones(guild_id: int) -> bool:
    return bool(get_setting(guild_id, 'subtract_ones'))


def is_wod(guild_id: int) -> bool:
    return get_system(guild_id) == SYSTEM_WOD


# --- Validated setters (used by the !config command) -----------------------

def set_system(guild_id: int, system: str) -> str:
    """Switch roll system. Also moves the die to that system's default unless
    the guild has already chosen one explicitly."""
    system = system.strip().lower()
    if system not in SYSTEMS:
        raise SettingError(f'Unknown system. Pick one of: {", ".join(SYSTEMS)}.')
    overrides: dict = GuildConfig().get(str(guild_id), {})
    set_setting(guild_id, 'system', system)
    if 'die' not in overrides:
        set_setting(guild_id, 'die', SYSTEM_DIE[system])
    return system


def set_die(guild_id: int, sides: int) -> int:
    if sides < 2:
        raise SettingError('A die needs at least 2 sides.')
    if sides > MAX_SIDES:
        raise SettingError(f'Die is too big — the limit is d{MAX_SIDES}.')
    set_setting(guild_id, 'die', sides)
    return sides


def set_difficulty(guild_id: int, difficulty: int) -> int:
    if difficulty < 1:
        raise SettingError('Difficulty must be at least 1.')
    die = get_die(guild_id)
    if difficulty > die:
        raise SettingError(
            f'Difficulty {difficulty} is impossible on a d{die} — '
            f'lower it, or raise the die with `!config die`.'
        )
    set_setting(guild_id, 'difficulty', difficulty)
    return difficulty


def set_subtract_ones(guild_id: int, enabled: bool) -> bool:
    set_setting(guild_id, 'subtract_ones', enabled)
    return enabled


def max_pool() -> int:
    """Largest dice pool a bare-count roll may request."""
    return MAX_DICE
