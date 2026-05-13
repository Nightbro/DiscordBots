import json
import logging

from .config import REACTION_CONFIG_FILE

log = logging.getLogger('music-bot.reaction_config')


def load_reaction_config() -> dict:
    if REACTION_CONFIG_FILE.exists():
        return json.loads(REACTION_CONFIG_FILE.read_text(encoding='utf-8'))
    return {}


def save_reaction_config(data: dict):
    REACTION_CONFIG_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8'
    )


def _key(message_id: int, emoji: str) -> str:
    return f'{message_id}:{emoji}'


def get_watches(guild_id: int) -> dict:
    """Return all watches for a guild as {key: entry}."""
    return load_reaction_config().get(str(guild_id), {})


def add_watch(guild_id: int, message_id: int, emoji: str, channel_id: int, response: str = None):
    config = load_reaction_config()
    entry = {'channel_id': channel_id}
    if response:
        entry['response'] = response
    config.setdefault(str(guild_id), {})[_key(message_id, emoji)] = entry
    save_reaction_config(config)


def remove_watch(guild_id: int, message_id: int, emoji: str) -> bool:
    """Remove a watch. Returns True if it existed."""
    config = load_reaction_config()
    entry = config.get(str(guild_id), {}).pop(_key(message_id, emoji), None)
    if entry is not None:
        save_reaction_config(config)
        return True
    return False
