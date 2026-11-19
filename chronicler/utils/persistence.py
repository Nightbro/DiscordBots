"""JSON-backed stores.

Writes are atomic: data goes to a temp file beside the target and is then
moved into place with os.replace, which is atomic on both POSIX and Windows.
A crash mid-write therefore leaves the previous version intact rather than a
truncated file. Chronicler needs this where the other bots did not — a
reminder loop writing on a timer runs alongside players editing their own
records, so a half-written file is a live possibility rather than a
theoretical one.

Each concern gets its own file and its own subclass, so a problem in one
store cannot take the others down with it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class BaseConfig:
    """JSON-backed store base. Subclasses set `path` as a class or instance var."""

    path: Path

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with open(self.path, encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # A corrupt or unreadable file must not take the bot down —
            # fall back to defaults rather than raising at command time.
            return {}

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f'{self.path.name}.tmp')
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            # Never leave a stray temp file behind — on any failure the
            # original file is still the one on disk.
            tmp.unlink(missing_ok=True)
            raise

    def get(self, key: str, default: Any = None) -> Any:
        return self.load().get(key, default)

    def set(self, key: str, value: Any) -> None:
        data = self.load()
        data[key] = value
        self.save(data)

    def delete(self, key: str) -> bool:
        """Remove a key. Returns True if it existed."""
        data = self.load()
        if key not in data:
            return False
        del data[key]
        self.save(data)
        return True

    def all(self) -> dict:
        return self.load()


class GuildConfig(BaseConfig):
    """Per-guild settings, persisted to guild_config.json."""

    def __init__(self) -> None:
        # Imported here, not at module level, for two reasons: it breaks the
        # config -> persistence import cycle, and it means the path is read at
        # construction time, so tests can redirect the store by patching
        # utils.config.GUILD_CONFIG_FILE.
        from utils.config import GUILD_CONFIG_FILE
        self.path = GUILD_CONFIG_FILE


class ArchiveConfig(BaseConfig):
    """Channel export records, persisted to archive_config.json.

    This is the audit trail of what was exported. It is deliberately *not* the
    authority on what may be deleted — that lives in each bundle's own
    manifest, so nothing can be purged unless the backup holding it is present.
    """

    def __init__(self) -> None:
        from utils.config import ARCHIVE_CONFIG_FILE
        self.path = ARCHIVE_CONFIG_FILE
