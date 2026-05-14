import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR          = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR     = BASE_DIR / 'downloads'
LOGS_DIR          = BASE_DIR / 'logs'
INTRO_SOUNDS_DIR  = BASE_DIR / 'intro_sounds'
PLAYLISTS_FILE    = BASE_DIR / 'playlists.json'
INTRO_CONFIG_FILE = BASE_DIR / 'intro_config.json'
_COOKIES_FILE     = BASE_DIR / 'cookies.txt'

SOUNDBOARD_DIR        = BASE_DIR / 'soundboard'
SOUNDBOARD_CONFIG_FILE = BASE_DIR / 'soundboard_config.json'

DOWNLOADS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
INTRO_SOUNDS_DIR.mkdir(exist_ok=True)
SOUNDBOARD_DIR.mkdir(exist_ok=True)

_INTRO_FILE         = BASE_DIR / os.getenv('INTRO_MP3', 'intro.mp3')
_INTRO_ON_BOT_JOIN  = os.getenv('INTRO_ON_BOT_JOIN',  'true').lower() == 'true'
_INTRO_ON_USER_JOIN = os.getenv('INTRO_ON_USER_JOIN', 'true').lower() == 'true'

# Audio formats accepted as Discord attachments (FFmpeg handles all of these natively).
AUDIO_EXTS = frozenset({'.mp3', '.ogg', '.opus', '.wav', '.flac', '.m4a', '.aac'})
