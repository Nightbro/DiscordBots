import subprocess
from pathlib import Path

import yaml
from dotenv import load_dotenv

_HERE = Path(__file__).parent.parent  # night-roller/
load_dotenv(_HERE / '.env')

with open(_HERE / 'config.yaml', encoding='utf-8') as _f:
    _cfg = yaml.safe_load(_f)

_bot = _cfg['bot']
_dice = _cfg['dice']

# Bot identity
BOT_NAME: str = _bot['name']
PREFIX: str = _bot['prefix']
COLOR: int = _bot['color']
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

# Dice settings
DEFAULT_EXPRESSION: str = _dice['default_expression']
MAX_DICE: int = _dice['max_dice']
MAX_SIDES: int = _dice['max_sides']
MAX_GROUPS: int = _dice['max_groups']
SHOW_ROLLS: bool = _dice['show_rolls']

# Paths
BASE_DIR: Path = _HERE
DATA_DIR: Path = BASE_DIR / 'data'
LOGS_DIR: Path = DATA_DIR / 'logs'

for _d in (LOGS_DIR,):
    _d.mkdir(parents=True, exist_ok=True)
