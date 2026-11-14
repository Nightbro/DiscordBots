import subprocess
from pathlib import Path

import yaml
from dotenv import load_dotenv

_HERE = Path(__file__).parent.parent  # chronicler/
load_dotenv(_HERE / '.env')

with open(_HERE / 'config.yaml', encoding='utf-8') as _f:
    _cfg = yaml.safe_load(_f)

_bot = _cfg['bot']
_dice = _cfg['dice']

# Bot identity
BOT_NAME: str = _bot['name']
PREFIX: str = _bot['prefix']
COLOR: int = _bot['color']
# Empty until the Discord application exists — the invite reply says so
# rather than sending a broken link.
INVITE_URL: str = _bot['invite_url']


def _git(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, cwd=_HERE, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ''


_version_base: str = _bot.get('version', '1.0')
_commit_count: str = _git(['git', 'rev-list', '--count', 'HEAD']) or '0'
_commit_hash: str = _git(['git', 'rev-parse', '--short', 'HEAD']) or 'unknown'
VERSION: str = f'{_version_base}.{_commit_count} ({_commit_hash})'

# Emojis
EMOJI_DICE: str = _bot['emojis']['dice']
EMOJI_CRIT: str = _bot['emojis']['crit']
EMOJI_FAIL: str = _bot['emojis']['fail']

# Dice settings — global defaults, overridable per guild via utils/guild_config
DEFAULT_SYSTEM: str = _dice['default_system']
DEFAULT_DIE: int = _dice['default_die']
DEFAULT_DIFFICULTY: int = _dice['default_difficulty']
DEFAULT_SUBTRACT_ONES: bool = _dice['default_subtract_ones']
MAX_DICE: int = _dice['max_dice']
MAX_SIDES: int = _dice['max_sides']
MAX_GROUPS: int = _dice['max_groups']
SHOW_ROLLS: bool = _dice['show_rolls']

# Paths — every runtime path hangs off BASE_DIR. Nothing in cogs/ may build a
# data path of its own; add a constant here instead.
BASE_DIR: Path = _HERE
DATA_DIR: Path = BASE_DIR / 'data'
LOGS_DIR: Path = DATA_DIR / 'logs'
GUILD_CONFIG_FILE: Path = DATA_DIR / 'guild_config.json'

# Directories are created on import; JSON files are created lazily on first
# save, so a fresh install starts with none of them.
for _d in (LOGS_DIR,):
    _d.mkdir(parents=True, exist_ok=True)
