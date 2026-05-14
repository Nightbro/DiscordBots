from pathlib import Path

import yaml
from dotenv import load_dotenv

_HERE = Path(__file__).parent.parent  # echo-bot/
load_dotenv(_HERE / '.env')

with open(_HERE / 'config.yaml', encoding='utf-8') as _f:
    _cfg = yaml.safe_load(_f)

_bot = _cfg['bot']
_audio = _cfg['audio']
_intros = _cfg['intros']
_tts = _cfg['tts']

# Bot identity
BOT_NAME: str = _bot['name']
PREFIX: str = _bot['prefix']
COLOR: int = _bot['color']

# Emojis
EMOJI_YES: str = _bot['emojis']['yes']
EMOJI_NO: str = _bot['emojis']['no']
EMOJI_MUSIC: str = _bot['emojis']['music']
EMOJI_SPEAKING: str = _bot['emojis']['speaking']
EMOJI_LOADING: str = _bot['emojis']['loading']

# Audio settings
PANEL_TIMEOUT: int = _audio['panel_timeout']
MAX_QUEUE: int = _audio['max_queue']

# Intro settings
INTRO_ON_BOT_JOIN: bool = _intros['on_bot_join']
INTRO_ON_USER_JOIN: bool = _intros['on_user_join']

# TTS settings
TTS_DEFAULT_VOICE: str = _tts['default_voice']
TTS_DEFAULT_RATE: str = _tts['default_rate']

# Paths
BASE_DIR: Path = _HERE
DATA_DIR: Path = BASE_DIR / 'data'
DOWNLOADS_DIR: Path = DATA_DIR / 'downloads'
INTRO_SOUNDS_DIR: Path = DATA_DIR / 'intro_sounds'
SOUNDBOARD_DIR: Path = DATA_DIR / 'soundboard'
LOGS_DIR: Path = DATA_DIR / 'logs'
PLAYLISTS_FILE: Path = DATA_DIR / 'playlists.json'
INTRO_CONFIG_FILE: Path = DATA_DIR / 'intro_config.json'
SOUNDBOARD_CONFIG_FILE: Path = DATA_DIR / 'soundboard_config.json'

for _d in (DOWNLOADS_DIR, INTRO_SOUNDS_DIR, SOUNDBOARD_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
