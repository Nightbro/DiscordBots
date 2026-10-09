"""
Per-guild track library: songs uploaded to the bot and kept on the server.

Files live in LIBRARY_DIR/<guild_id>/<slug>.<ext>; metadata in data/library_config.json:
{
    "<guild_id>": {
        "<slug>": {
            "title": "Halloween",
            "file": "halloween.mp3",
            "size": 3061586,
            "duration": 192,          # seconds, None if ffprobe is unavailable
            "added_by": 555,          # user id
            "added_by_name": "Ivan",
            "added_at": "2026-10-09T18:30:00",
            "plays": 4
        }
    }
}

Libraries are per guild: one server never sees another's uploads. Numbering used
by `#N` selection is the position in `track_list()`, i.e. sorted by title, so it
is stable without storing any per-channel state.

No Discord types here — cogs handle presentation.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from utils.config import (
    LIBRARY_CONFIG_FILE,
    LIBRARY_DIR,
    LIBRARY_MAX_TOTAL_MB,
    LIBRARY_MAX_TRACKS,
)
from utils.guild_state import Track
from utils.persistence import LibraryConfig

log = logging.getLogger(__name__)

_SLUG_STRIP = re.compile(r'[^a-z0-9]+')


class LibraryError(Exception):
    """Raised for conditions the user should see: quota reached, name taken, etc."""


# ---------------------------------------------------------------------------
# Paths and names
# ---------------------------------------------------------------------------

def slugify(title: str) -> str:
    """Filesystem- and command-safe key for a title ('Hällo World!' → 'hallo-world')."""
    folded = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode()
    slug = _SLUG_STRIP.sub('-', folded.lower()).strip('-')
    return slug or 'track'


def guild_dir(guild_id: int) -> Path:
    path = LIBRARY_DIR / str(guild_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def track_path(guild_id: int, slug: str) -> Path | None:
    meta = get_track(guild_id, slug)
    if not meta:
        return None
    path = guild_dir(guild_id) / meta['file']
    return path if path.exists() else None


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_tracks(guild_id: int) -> dict[str, dict]:
    """All {slug: meta} for a guild."""
    return LibraryConfig().get(str(guild_id), {})


def get_track(guild_id: int, slug: str) -> dict | None:
    return get_tracks(guild_id).get(slug)


def track_list(guild_id: int) -> list[tuple[str, dict]]:
    """(slug, meta) pairs sorted by title — the order `#N` refers to."""
    return sorted(get_tracks(guild_id).items(), key=lambda kv: kv[1]['title'].lower())


def total_size(guild_id: int) -> int:
    return sum(meta.get('size', 0) for meta in get_tracks(guild_id).values())


def find(guild_id: int, query: str) -> tuple[str, dict] | None:
    """Best single match for a query: exact slug/title first, then a partial title match."""
    matches = find_all(guild_id, query)
    return matches[0] if matches else None


def find_all(guild_id: int, query: str) -> list[tuple[str, dict]]:
    """Matches for a query, best first. Exact slug/title, then titles containing it."""
    needle = query.strip().lower()
    if not needle:
        return []
    tracks = track_list(guild_id)
    exact = [
        (slug, meta) for slug, meta in tracks
        if slug == needle or meta['title'].lower() == needle
    ]
    partial = [
        (slug, meta) for slug, meta in tracks
        if (slug, meta) not in exact and needle in meta['title'].lower()
    ]
    return exact + partial


def is_exact_match(query: str, slug: str, meta: dict) -> bool:
    needle = query.strip().lower()
    return needle == slug or needle == meta['title'].lower()


def parse_index(query: str) -> int | None:
    """'#3' → 3 (1-based). Returns None if the query is not an index reference."""
    text = query.strip()
    if not text.startswith('#'):
        return None
    rest = text[1:].strip()
    return int(rest) if rest.isdigit() and int(rest) > 0 else None


def by_index(guild_id: int, index: int) -> tuple[str, dict] | None:
    tracks = track_list(guild_id)
    return tracks[index - 1] if 1 <= index <= len(tracks) else None


def resolve(guild_id: int, query: str) -> tuple[str, dict] | None:
    """Resolve '#N' or a name to a library track."""
    index = parse_index(query)
    if index is not None:
        return by_index(guild_id, index)
    return find(guild_id, query)


def to_track(guild_id: int, slug: str) -> Track | None:
    """Build a playable Track for a library entry."""
    meta = get_track(guild_id, slug)
    path = track_path(guild_id, slug)
    if not meta or path is None:
        return None
    return Track(
        title=meta['title'],
        url=str(path),
        file_path=path,
        duration=meta.get('duration'),
        source_id=f'lib:{slug}',
    )


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def check_quota(guild_id: int, incoming_size: int) -> None:
    """Raise LibraryError if adding incoming_size bytes would exceed a limit."""
    tracks = get_tracks(guild_id)
    if len(tracks) >= LIBRARY_MAX_TRACKS:
        raise LibraryError(f'track_limit:{LIBRARY_MAX_TRACKS}')
    limit = LIBRARY_MAX_TOTAL_MB * 1024 * 1024
    if total_size(guild_id) + incoming_size > limit:
        raise LibraryError(f'size_limit:{LIBRARY_MAX_TOTAL_MB}')


def add_track(
    guild_id: int,
    title: str,
    file_path: Path,
    *,
    duration: int | None,
    added_by: int,
    added_by_name: str,
) -> str:
    """Register an already-saved file. Returns its slug.

    The caller saves the upload into `guild_dir(guild_id)` first; on a name clash
    this raises before touching the index.
    """
    slug = slugify(title)
    if slug in get_tracks(guild_id):
        raise LibraryError(f'name_taken:{slug}')
    cfg = LibraryConfig()
    guild_tracks: dict = cfg.get(str(guild_id), {})
    guild_tracks[slug] = {
        'title': title,
        'file': file_path.name,
        'size': file_path.stat().st_size if file_path.exists() else 0,
        'duration': duration,
        'added_by': added_by,
        'added_by_name': added_by_name,
        'added_at': datetime.now().isoformat(timespec='seconds'),
        'plays': 0,
    }
    cfg.set(str(guild_id), guild_tracks)
    return slug


def remove_track(guild_id: int, slug: str) -> bool:
    """Drop a track and delete its file. Returns False if it wasn't there."""
    cfg = LibraryConfig()
    guild_tracks: dict = cfg.get(str(guild_id), {})
    meta = guild_tracks.pop(slug, None)
    if meta is None:
        return False
    cfg.set(str(guild_id), guild_tracks)
    (guild_dir(guild_id) / meta['file']).unlink(missing_ok=True)
    return True


def rename_track(guild_id: int, slug: str, new_title: str) -> str:
    """Retitle a track, keeping its file. Returns the new slug."""
    cfg = LibraryConfig()
    guild_tracks: dict = cfg.get(str(guild_id), {})
    meta = guild_tracks.get(slug)
    if meta is None:
        raise LibraryError(f'not_found:{slug}')
    new_slug = slugify(new_title)
    if new_slug != slug and new_slug in guild_tracks:
        raise LibraryError(f'name_taken:{new_slug}')
    meta['title'] = new_title
    del guild_tracks[slug]
    guild_tracks[new_slug] = meta
    cfg.set(str(guild_id), guild_tracks)
    return new_slug


def bump_plays(guild_id: int, slug: str) -> None:
    cfg = LibraryConfig()
    guild_tracks: dict = cfg.get(str(guild_id), {})
    meta = guild_tracks.get(slug)
    if meta is None:
        return
    meta['plays'] = meta.get('plays', 0) + 1
    cfg.set(str(guild_id), guild_tracks)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def probe_duration(path: Path) -> int | None:
    """Track length in seconds via ffprobe, or None if it can't be determined."""
    try:
        proc = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        return int(float(out.decode().strip()))
    except Exception as exc:
        log.warning('ffprobe failed for %s: %s', path, exc)
        return None


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return '—'
    return f'{seconds // 60}:{seconds % 60:02d}'


# Re-exported so cogs don't need utils.config for these
MAX_TRACKS = LIBRARY_MAX_TRACKS
MAX_TOTAL_MB = LIBRARY_MAX_TOTAL_MB
CONFIG_FILE = LIBRARY_CONFIG_FILE
