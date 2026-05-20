"""
Soundboard configuration helpers.

State is stored in data/soundboard_config.json via SoundboardConfig (persistence.py).

Schema:
{
    "boom": {"emoji": "💥", "file": "boom.mp3"},
    "airhorn": {"emoji": "📯", "file": "airhorn.mp3"},
    ...
}
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from utils.config import SOUNDBOARD_DIR
from utils.persistence import SoundboardConfig

_DEFAULT_EMOJI = '🔊'


def get_sounds() -> dict[str, dict]:
    """Return the full {name: meta} mapping."""
    return SoundboardConfig().all()


def get_sound(name: str) -> Optional[dict]:
    """Return meta dict for a sound, or None if not found."""
    return SoundboardConfig().get(name)


def add_sound(name: str, filename: str, emoji: str = _DEFAULT_EMOJI, short: str = '') -> None:
    cfg = SoundboardConfig()
    entry: dict = {'emoji': emoji, 'file': filename}
    if short:
        entry['short'] = short
    cfg.set(name, entry)


def find_sound(trigger: str) -> tuple[str, dict] | None:
    """Case-insensitive lookup by full name OR short trigger. Returns (name, meta) or None."""
    needle = trigger.lower()
    for name, meta in SoundboardConfig().all().items():
        if name.lower() == needle:
            return name, meta
        s = meta.get('short', '')
        if s and s.lower() == needle:
            return name, meta
    return None


def remove_sound(name: str) -> bool:
    """Remove a sound entry. File deletion is the caller's responsibility. Returns True if it existed."""
    return SoundboardConfig().delete(name)


def get_sound_path(name: str) -> Optional[Path]:
    """Return the filesystem Path for a sound, or None if not configured."""
    meta = get_sound(name)
    if not meta:
        return None
    p = SOUNDBOARD_DIR / meta['file']
    return p if p.exists() else None


def sound_exists(name: str) -> bool:
    return get_sound(name) is not None
