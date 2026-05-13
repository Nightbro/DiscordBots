import re
import ssl
import logging
import urllib.request
from pathlib import Path

import certifi
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, ID3NoHeaderError

from .config import DOWNLOADS_DIR, _COOKIES_FILE

log = logging.getLogger('music-bot.downloader')

# Direct SSL context for urllib calls (not routed through the monkey-patch)
_SSL_CTX = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_SSL_CTX.load_verify_locations(certifi.where())

# --- URL patterns ---
SUNO_RE = re.compile(
    r'(?:https?://)?(?:www\.)?(?:suno\.com|app\.suno\.ai)/(?:song|s)/([a-zA-Z0-9-]+)'
)
SUNO_UUID_RE = re.compile(
    r'/song/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
)
YOUTUBE_ID_RE = re.compile(
    r'(?:youtube\.com/(?:watch\?.*?v=|shorts/)|youtu\.be/)([a-zA-Z0-9_-]{11})'
)

# --- yt-dlp options ---
class _YDLLogger:
    def debug(self, msg):
        if not msg.startswith('[debug] '):
            log.debug('yt-dlp: %s', msg)
    def info(self, msg):
        log.info('yt-dlp: %s', msg)
    def warning(self, msg):
        log.warning('yt-dlp: %s', msg)
    def error(self, msg):
        log.error('yt-dlp: %s', msg)

YDL_INFO = {
    'format': 'best',
    'noplaylist': True,
    'quiet': True,
    'logger': _YDLLogger(),
    'default_search': 'ytsearch',
    **({'cookiefile': str(_COOKIES_FILE)} if _COOKIES_FILE.exists() else {}),
}

YDL_DOWNLOAD = {
    **YDL_INFO,
    'outtmpl': str(DOWNLOADS_DIR / '%(id)s.%(ext)s'),
    'postprocessors': [
        {
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        },
        {
            'key': 'FFmpegMetadata',
            'add_metadata': True,
        },
    ],
}

FFMPEG_OPTIONS = {'options': '-vn'}

# --- Helpers ---

def is_suno_url(query: str) -> bool:
    return bool(SUNO_RE.search(query))


def duration_tag(seconds) -> str:
    if not seconds:
        return ''
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    t = f'{h}:{m:02}:{s:02}' if h else f'{m}:{s:02}'
    return f' `[{t}]`'


def tag_mp3(path: Path, title: str, artist: str = 'Suno AI', album: str = 'Suno'):
    try:
        try:
            tags = ID3(str(path))
        except ID3NoHeaderError:
            tags = ID3()
        tags['TIT2'] = TIT2(encoding=3, text=title)
        tags['TPE1'] = TPE1(encoding=3, text=artist)
        tags['TALB'] = TALB(encoding=3, text=album)
        tags.save(str(path))
    except Exception as e:
        log.warning('Could not write ID3 tags to %s: %s', path.name, e)


def read_cached_mp3(path: Path, webpage_url: str = '') -> dict:
    title = 'Unknown'
    duration = 0
    try:
        audio = MP3(str(path))
        duration = int(audio.info.length)
    except Exception:
        pass
    try:
        tags = ID3(str(path))
        if 'TIT2' in tags:
            title = str(tags['TIT2'])
    except Exception:
        pass
    log.debug('Cache hit: %s (%s)', title, path.name)
    return {
        'file': str(path),
        'title': title,
        'duration': duration,
        'webpage_url': webpage_url,
        'from_cache': True,
    }


# --- Downloaders ---

def download_youtube(query: str) -> dict:
    m = YOUTUBE_ID_RE.search(query)
    if m:
        cached = DOWNLOADS_DIR / f'{m.group(1)}.mp3'
        if cached.exists():
            return read_cached_mp3(cached, query)

    log.info('Fetching info for: %s', query)
    with yt_dlp.YoutubeDL(YDL_INFO) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info:
            info = info['entries'][0]

    video_id   = info['id']
    title      = info.get('title', 'Unknown')
    duration   = info.get('duration', 0)
    source_url = info.get('webpage_url', query)
    cached     = DOWNLOADS_DIR / f'{video_id}.mp3'

    if cached.exists():
        track = read_cached_mp3(cached, source_url)
        track['title'] = title
        track['duration'] = duration
        return track

    log.info('Downloading: %s', title)
    with yt_dlp.YoutubeDL(YDL_DOWNLOAD) as ydl:
        ydl.extract_info(source_url, download=True)
    log.info('Download complete: %s', title)

    return {
        'file': str(cached),
        'title': title,
        'duration': duration,
        'webpage_url': source_url,
        'from_cache': False,
    }


def download_suno(url: str) -> dict:
    m = SUNO_UUID_RE.search(url)
    if m:
        cached = DOWNLOADS_DIR / f'{m.group(1)}.mp3'
        if cached.exists():
            track = read_cached_mp3(cached, url)
            track.setdefault('artist', 'Suno AI')
            return track

    title     = 'Unknown Suno Track'
    artist    = 'Suno AI'
    duration  = 0
    song_uuid = None

    log.info('Resolving Suno URL: %s', url)
    try:
        with yt_dlp.YoutubeDL(YDL_INFO) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                info = info['entries'][0]
        title    = info.get('title', title)
        artist   = info.get('uploader') or info.get('creator') or artist
        duration = info.get('duration') or 0
        raw_id   = info.get('id', '')
        if re.fullmatch(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', raw_id
        ):
            song_uuid = raw_id
        else:
            m2 = SUNO_UUID_RE.search(info.get('webpage_url', ''))
            if m2:
                song_uuid = m2.group(1)
    except Exception as e:
        log.warning('yt-dlp could not resolve Suno URL (%s), falling back to URL parse', e)

    if not song_uuid:
        m2 = SUNO_UUID_RE.search(url)
        if m2:
            song_uuid = m2.group(1)

    if not song_uuid:
        raise ValueError(
            f'Could not resolve Suno song UUID from: {url}\n'
            'Make sure the song is public and the URL is correct.'
        )

    cached = DOWNLOADS_DIR / f'{song_uuid}.mp3'

    if cached.exists():
        track = read_cached_mp3(cached, url)
        track['artist'] = artist
        return track

    log.info('Downloading Suno track: %s (%s)', title, song_uuid)
    cdn_url = f'https://cdn1.suno.ai/{song_uuid}.mp3'
    req = urllib.request.Request(cdn_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as resp:
        cached.write_bytes(resp.read())
    tag_mp3(cached, title=title, artist=artist)
    log.info('Download complete: %s', title)

    return {
        'file': str(cached),
        'title': title,
        'artist': artist,
        'duration': duration,
        'webpage_url': url,
        'from_cache': False,
    }


def download_track(query: str) -> dict:
    if is_suno_url(query):
        return download_suno(query)
    return download_youtube(query)
