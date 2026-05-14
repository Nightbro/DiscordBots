import asyncio
import logging
import re
from pathlib import Path

import yt_dlp

from utils.config import DOWNLOADS_DIR
from utils.guild_state import Track

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
    async def _resolve_search(query: str) -> Track:
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
