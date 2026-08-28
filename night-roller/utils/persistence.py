import json
from pathlib import Path
from typing import Any


class BaseConfig:
    """JSON-backed config base. Subclasses set `path` as a class or instance var."""

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
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

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
        from utils.config import GUILD_CONFIG_FILE
        self.path = GUILD_CONFIG_FILE
