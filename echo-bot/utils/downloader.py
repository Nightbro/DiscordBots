import asyncio
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

_SUNO_UUID_RE = re.compile(
    r'/(?:song|s)/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
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
            cached = DOWNLOADS_DIR / f'{track.source_id}.mp3'
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
        """Download a Suno track by fetching the CDN MP3 directly via urllib."""
        uuid = track.source_id
        if not uuid:
            m = _SUNO_UUID_RE.search(track.url)
            if m:
                uuid = m.group(1)
        if not uuid:
            raise ValueError(f'Could not extract Suno UUID from: {track.url}')

        cached = DOWNLOADS_DIR / f'{uuid}.mp3'
        if cached.exists():
            track.file_path = cached
            return cached

        cdn_url = f'https://cdn1.suno.ai/{uuid}.mp3'
        log.info('Downloading Suno track %s from CDN', uuid)
        req = urllib.request.Request(cdn_url, headers={'User-Agent': 'Mozilla/5.0'})

        def _fetch() -> None:
            with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as resp:
                cached.write_bytes(resp.read())

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _fetch)
        track.file_path = cached
        return cached

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
