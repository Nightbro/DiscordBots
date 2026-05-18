"""
Localisation helper.

Usage:
    from utils.i18n import t
    t('music.skip.skipped', guild_id, title='Never Gonna Give You Up')

Keys use dot notation and map to the nested structure in locales/<code>.yaml.
If a key is missing in the guild's locale, falls back to 'en'.
If missing in 'en' too, returns the key itself and logs a warning.

Two file layers per locale (both merged into one dict):
  locales/<code>.yaml         — short UI strings (errors, confirmations, labels)
  locales/banners/<code>.yaml — help/banner section content (longer, easier to find)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

_LOCALES_DIR = Path(__file__).parent.parent / 'locales'
_BANNERS_DIR = _LOCALES_DIR / 'banners'
_DEFAULT_LOCALE = 'en'

# Loaded locale data, keyed by locale code
_cache: dict[str, dict] = {}


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base, returning a new dict."""
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load(locale: str) -> dict:
    if locale not in _cache:
        data: dict = {}
        path = _LOCALES_DIR / f'{locale}.yaml'
        if path.exists():
            with open(path, encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
        banners_path = _BANNERS_DIR / f'{locale}.yaml'
        if banners_path.exists():
            with open(banners_path, encoding='utf-8') as f:
                data = _deep_merge(data, yaml.safe_load(f) or {})
        _cache[locale] = data
    return _cache[locale]


def _lookup(data: dict, parts: list[str]) -> Any:
    for part in parts:
        if not isinstance(data, dict):
            return None
        data = data.get(part)
        if data is None:
            return None
    return data


def t(msg_key: str, guild_id: int = 0, **kwargs: Any) -> str:
    """Return the localised string for msg_key, formatted with kwargs."""
    # Lazy import to avoid circular dependency at module load time
    from utils.guild_config import get_locale
    locale = get_locale(guild_id) if guild_id else _DEFAULT_LOCALE

    parts = msg_key.split('.')

    value = _lookup(_load(locale), parts)
    if value is None and locale != _DEFAULT_LOCALE:
        value = _lookup(_load(_DEFAULT_LOCALE), parts)
    if value is None:
        log.warning('Missing i18n key: %s (locale: %s)', msg_key, locale)
        return msg_key

    text = str(value)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError as exc:
            log.warning('Missing format arg %s for i18n key %s', exc, msg_key)
    return text


def supported_locales() -> list[str]:
    """Return locale codes for which a root YAML file exists."""
    return sorted(p.stem for p in _LOCALES_DIR.glob('*.yaml'))


def reload_cache() -> None:
    """Clear in-memory cache. Called by dev hot-reload."""
    _cache.clear()
