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
_SUNO_EXTS = ('.m4a', '.mp3')
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


class Downloader:
    @staticmethod
    def is_suno_url(url: str) -> bool:
        return bool(_SUNO_RE.match(url))

    @staticmethod
    async def resolve(query: str) -> Track:
        """Return a Track with metadata. Does not download the audio file."""
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
    async def _download_suno(track: Track) -> Path:
        """Download a Suno track.

        Suno's clip API lists the playable file under ``media_urls`` (an .m4a on
        CloudFront). The old ``cdn1.suno.ai/{uuid}.mp3`` URL now returns 403, so it
        is only tried as a last resort.
        """
        uuid, share_qs = Downloader._suno_id(track)

        for ext in _SUNO_EXTS:
            cached = DOWNLOADS_DIR / f'{uuid}{ext}'
            if cached.exists():
                track.file_path = cached
                return cached

        loop = asyncio.get_event_loop()
        candidates = await loop.run_in_executor(None, Downloader._suno_audio_urls, uuid)
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
    def _suno_audio_urls(uuid: str) -> list[str]:
        """Ask Suno's clip API for playable audio URLs. Returns [] on failure."""
        req = urllib.request.Request(
            _SUNO_CLIP_API.format(uuid=uuid), headers={'User-Agent': _HTTP_UA}
        )
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            log.warning('Suno clip API lookup failed for %s: %s', uuid, e)
            return []
        urls = [m['url'] for m in data.get('media_urls') or [] if m.get('url')]
        audio_url = data.get('audio_url') or ''
        if audio_url and not audio_url.endswith('/forbidden'):
            urls.append(audio_url)
        return urls

    @staticmethod
    def _http_fetch(url: str, dest: Path) -> None:
        req = urllib.request.Request(url, headers={'User-Agent': _HTTP_UA})
        with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as resp:
            data = resp.read()
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
