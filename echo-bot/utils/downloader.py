import asyncio
import json
import logging
import re
import ssl
import urllib.request
from pathlib import Path

import certifi
import yt_dlp

from utils.config import DOWNLOADS_DIR
from utils.guild_state import Track

_SSL_CTX = ssl.create_default_context(cafile=certifi.where())

_UUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

_SUNO_CLIP_API = 'https://studio-api.prod.suno.com/api/clip/{uuid}'
_SUNO_LEGACY_CDN = 'https://cdn1.suno.ai/{uuid}.mp3'
_SUNO_EXTS = ('.mp4', '.mp3')
# Earlier builds cached Suno's media_urls .m4a, which is not playable audio.
_SUNO_STALE_EXTS = ('.m4a',)
_HTTP_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/140.0 Safari/537.36'
)

log = logging.getLogger(__name__)

_SUNO_RE = re.compile(r'https?://(?:www\.)?suno\.(?:com|ai)/')

_INFO_OPTS: dict = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
}

_DL_OPTS: dict = {
    'format': 'bestaudio/best',
    'outtmpl': str(DOWNLOADS_DIR / '%(id)s.%(ext)s'),
    'quiet': True,
    'no_warnings': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}


def _looks_like_audio(data: bytes) -> bool:
    """Cheap container sniff: MP4 ('ftyp' box) or MP3 (ID3 tag / frame sync)."""
    return (
        data[4:8] == b'ftyp'
        or data[:3] == b'ID3'
        or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)
    )


class Downloader:
    @staticmethod
    def is_suno_url(url: str) -> bool:
        return bool(_SUNO_RE.match(url))

    @staticmethod
    async def resolve(query: str) -> Track:
        """Return a Track with metadata. Does not download the audio file."""
        if Downloader.is_suno_url(query):
            return await Downloader._resolve_suno(query)
        if query.startswith('http'):
            return await Downloader._resolve_url(query)
        return await Downloader._resolve_search(query)

    @staticmethod
    async def download(track: Track) -> Path:
        """Download track audio to DOWNLOADS_DIR. Uses cache if already present."""
        if track.file_path and track.file_path.exists():
            return track.file_path

        if track.source_id:
            # Strip any query params yt-dlp appends to the ID (e.g. ?sh=XXXXX)
            clean_id = track.source_id.split('?')[0]
            cached = DOWNLOADS_DIR / f'{clean_id}.mp3'
            if cached.exists():
                track.file_path = cached
                return cached

        if Downloader.is_suno_url(track.url):
            return await Downloader._download_suno(track)

        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(None, Downloader._ydl_download, track.url)
        track.file_path = path
        return path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    async def _resolve_url(url: str) -> Track:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, Downloader._ydl_info, url)
        # Playlists: take first entry
        if 'entries' in info:
            info = info['entries'][0]
        return Track(
            title=info.get('title', url),
            url=info.get('webpage_url') or info.get('url', url),
            duration=info.get('duration'),
            source_id=info.get('id'),
        )

    @staticmethod
    async def _resolve_suno(url: str) -> Track:
        """Resolve a Suno link via Suno's clip API.

        yt-dlp deliberately refuses suno.com (since 2026.08), so it is not used here.
        """
        loop = asyncio.get_event_loop()
        m = _UUID_RE.search(url)
        uuid = m.group(0) if m else await loop.run_in_executor(
            None, Downloader._suno_uuid_from_share_link, url
        )
        clip = await loop.run_in_executor(None, Downloader._suno_clip, uuid) or {}
        duration = (clip.get('metadata') or {}).get('duration')
        return Track(
            title=clip.get('title') or f'Suno {uuid}',
            url=f'https://suno.com/song/{uuid}',
            duration=int(duration) if duration else None,
            source_id=uuid,
        )

    @staticmethod
    def _suno_uuid_from_share_link(url: str) -> str:
        """Follow a share link (e.g. suno.com/s/AbC123) to find the song UUID."""
        req = urllib.request.Request(url, headers={'User-Agent': _HTTP_UA})
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            final_url = resp.geturl()
            m = _UUID_RE.search(final_url)
            if m:
                return m.group(0)
            html = resp.read().decode('utf-8', 'replace')
        m = re.search(r'/song/(' + _UUID_RE.pattern + ')', html)
        if not m:
            raise ValueError(f'Could not find a Suno song in: {url}')
        return m.group(1)

    @staticmethod
    async def _download_suno(track: Track) -> Path:
        """Download a Suno track.

        Suno's ``video_url`` (cdn1.suno.ai/{uuid}.mp4) is a plain MP4 with an AAC
        audio track; FFmpeg plays it with ``-vn``. The clip API's ``media_urls``
        file is not a playable container, and ``cdn1.suno.ai/{uuid}.mp3`` now
        returns 403, so that is only tried as a last resort.
        """
        uuid, share_qs = Downloader._suno_id(track)

        for ext in _SUNO_STALE_EXTS:
            (DOWNLOADS_DIR / f'{uuid}{ext}').unlink(missing_ok=True)
        for ext in _SUNO_EXTS:
            cached = DOWNLOADS_DIR / f'{uuid}{ext}'
            if cached.exists():
                track.file_path = cached
                return cached

        loop = asyncio.get_event_loop()
        clip = await loop.run_in_executor(None, Downloader._suno_clip, uuid)
        candidates = Downloader._suno_audio_urls(clip or {})
        legacy = _SUNO_LEGACY_CDN.format(uuid=uuid)
        candidates.append(f'{legacy}?{share_qs}' if share_qs else legacy)

        last_err: Exception | None = None
        for url in candidates:
            ext = Path(url.split('?')[0]).suffix.lower()
            dest = DOWNLOADS_DIR / f'{uuid}{ext if ext in _SUNO_EXTS else ".mp3"}'
            log.info('Downloading Suno track %s from %s', uuid, url)
            try:
                await loop.run_in_executor(None, Downloader._http_fetch, url, dest)
            except Exception as e:
                log.warning('Suno download failed from %s: %s', url, e)
                last_err = e
                continue
            track.file_path = dest
            return dest
        raise RuntimeError(f'Could not download Suno track {uuid}: {last_err}')

    @staticmethod
    def _suno_id(track: Track) -> tuple[str, str]:
        """Return (uuid, share query string) for a Suno track."""
        # yt-dlp may return source_id as "uuid?sh=XXXXX" or "uuid-1"
        source_id = track.source_id or ''
        m = _UUID_RE.search(source_id)
        if m:
            return m.group(0), source_id.partition('?')[2]
        m = _UUID_RE.search(track.url)
        if m:
            return m.group(0), ''
        raise ValueError(f'Could not extract Suno UUID from: {track.url}')

    @staticmethod
    def _suno_clip(uuid: str) -> dict | None:
        """Fetch a song's metadata from Suno's clip API. Returns None on failure."""
        req = urllib.request.Request(
            _SUNO_CLIP_API.format(uuid=uuid), headers={'User-Agent': _HTTP_UA}
        )
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                return json.loads(resp.read())
        except Exception as e:
            log.warning('Suno clip API lookup failed for %s: %s', uuid, e)
            return None

    @staticmethod
    def _suno_audio_urls(clip: dict) -> list[str]:
        """Playable URLs from a clip API response, best first."""
        urls = [clip['video_url']] if clip.get('video_url') else []
        audio_url = clip.get('audio_url') or ''
        if audio_url and not audio_url.endswith('/forbidden'):
            urls.append(audio_url)
        return urls

    @staticmethod
    def _http_fetch(url: str, dest: Path) -> None:
        req = urllib.request.Request(url, headers={'User-Agent': _HTTP_UA})
        with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as resp:
            data = resp.read()
        if not _looks_like_audio(data):
            raise ValueError(f'response from {url} is not an MP3/MP4 file')
        dest.write_bytes(data)

    @staticmethod
    async def _resolve_search(query: str) -> Track:
        lower = query.lower()
        if 'live' not in lower and 'music video' not in lower:
            query = query + ' audio'
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, Downloader._ydl_info, f'ytsearch1:{query}'
        )
        entries = result.get('entries') or []
        if not entries:
            raise ValueError(f'No results found for: {query}')
        info = entries[0]
        return Track(
            title=info.get('title', query),
            url=info.get('webpage_url') or info.get('url', ''),
            duration=info.get('duration'),
            source_id=info.get('id'),
        )

    @staticmethod
    def _ydl_info(url: str) -> dict:
        with yt_dlp.YoutubeDL(_INFO_OPTS) as ydl:
            return ydl.extract_info(url, download=False)

    @staticmethod
    def _ydl_download(url: str) -> Path:
        with yt_dlp.YoutubeDL(_DL_OPTS) as ydl:
            info = ydl.extract_info(url, download=True)
            if 'entries' in info:
                info = info['entries'][0]
            filename = ydl.prepare_filename(info)
            mp3_path = Path(filename).with_suffix('.mp3')
            return mp3_path if mp3_path.exists() else Path(filename)
