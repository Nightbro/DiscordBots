"""Channel archive: the domain model, the manifest, and the export record.

No Discord types here and no rendering — the cog fetches history and hands over
plain dataclasses, and utils/transcript.py turns them into documents.

The manifest is the safety interlock for deletion. It lists every message id an
export actually saved and it lives *inside the bundle*, so a purge can only run
against a backup that is present and readable. The export record in
archive_config.json is an audit trail, never the authority on what may be
deleted.
"""

from __future__ import annotations

import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from utils.config import ARCHIVE_MAX_BUNDLE_MB, ARCHIVE_MAX_MESSAGES
from utils.persistence import ArchiveConfig

MANIFEST_NAME = 'manifest.json'
MANIFEST_VERSION = 1

IMAGES_DIR = 'images'
FILES_DIR = 'files'

_IMAGE_EXTS = frozenset({'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tif', '.tiff'})

_SLUG_STRIP = re.compile(r'[^a-z0-9]+')


class ArchiveError(ValueError):
    """Raised for anything the user can fix — the message is shown to them."""


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

def safe_name(text: str, fallback: str = 'channel') -> str:
    """Filesystem-safe stem ('Général #1!' -> 'general-1')."""
    folded = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    slug = _SLUG_STRIP.sub('-', folded.lower()).strip('-')
    return slug or fallback


def is_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in _IMAGE_EXTS


def stored_name(message_id: int, index: int, filename: str) -> str:
    """Collision-proof name for one attachment inside the bundle.

    Message id plus position makes it unique without consulting what is already
    there; the original stem is kept only so a human can recognise the file.
    """
    suffix = Path(filename).suffix.lower()
    stem = safe_name(Path(filename).stem, fallback='file')[:40]
    return f'{message_id}-{index}-{stem}{suffix}'


def bundle_name(channel_name: str, when: datetime) -> str:
    return f'{safe_name(channel_name)}-{when.strftime("%Y%m%d-%H%M%S")}.zip'


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

@dataclass
class ArchivedAttachment:
    """One attachment, as saved into the bundle."""

    filename: str           # the name Discord had for it
    stored_as: str          # the name inside the bundle
    size: int               # bytes
    content_type: str = ''

    @property
    def is_image(self) -> bool:
        return is_image(self.filename)

    @property
    def path_in_bundle(self) -> str:
        return f'{IMAGES_DIR}/{self.stored_as}' if self.is_image else f'{FILES_DIR}/{self.stored_as}'


@dataclass
class ArchivedMessage:
    """One message, flattened to what the transcript needs."""

    id: int
    author_id: int
    author_name: str
    created_at: datetime
    content: str = ''
    edited: bool = False
    attachments: list[ArchivedAttachment] = field(default_factory=list)

    @property
    def images(self) -> list[ArchivedAttachment]:
        return [a for a in self.attachments if a.is_image]

    @property
    def files(self) -> list[ArchivedAttachment]:
        return [a for a in self.attachments if not a.is_image]

    @property
    def timestamp(self) -> str:
        return self.created_at.strftime('%Y-%m-%d %H:%M')


@dataclass
class Transcript:
    """Everything one export covers."""

    guild_name: str
    channel_name: str
    messages: list[ArchivedMessage] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def message_ids(self) -> list[int]:
        return [m.id for m in self.messages]

    @property
    def first_id(self) -> int | None:
        return self.messages[0].id if self.messages else None

    @property
    def last_id(self) -> int | None:
        return self.messages[-1].id if self.messages else None

    @property
    def attachment_count(self) -> int:
        return sum(len(m.attachments) for m in self.messages)

    @property
    def attachment_bytes(self) -> int:
        return sum(a.size for m in self.messages for a in m.attachments)


@dataclass
class RangeSpec:
    """A parsed, explicit export range. There is deliberately no default.

    `start_id` and `end_id` are **inclusive**, as the user typed them. Discord's
    own `after`/`before` are exclusive, so the cog offsets them by one when it
    calls history() — snowflakes are unique integers, so id-1 and id+1 are safe
    exclusive bounds that cannot skip or duplicate a real message.
    """

    limit: int | None = None        # "last N"
    start_id: int | None = None     # inclusive lower bound
    end_id: int | None = None       # inclusive upper bound

    def describe(self) -> str:
        if self.limit is not None:
            return f'the last {self.limit} messages'
        if self.start_id and self.end_id:
            return f'messages {self.start_id} to {self.end_id}'
        return f'everything from message {self.start_id} onwards'


# ---------------------------------------------------------------------------
# Limits — checked before anything is downloaded
# ---------------------------------------------------------------------------

def max_messages() -> int:
    return ARCHIVE_MAX_MESSAGES


def max_bundle_bytes() -> int:
    return ARCHIVE_MAX_BUNDLE_MB * 1024 * 1024


def check_message_count(count: int) -> None:
    if count > ARCHIVE_MAX_MESSAGES:
        raise ArchiveError(
            f'That range holds {count} messages — the limit is {ARCHIVE_MAX_MESSAGES}. '
            f'Export it in smaller pieces.'
        )


def check_attachment_bytes(total: int) -> None:
    if total > max_bundle_bytes():
        got = total / 1024 / 1024
        raise ArchiveError(
            f'Those attachments come to {got:.0f} MB — the limit is '
            f'{ARCHIVE_MAX_BUNDLE_MB} MB. Export a smaller range.'
        )


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def build_manifest(
    transcript: Transcript,
    *,
    guild_id: int,
    channel_id: int,
    exported_by: int,
    exported_by_name: str,
) -> dict:
    """The record that travels inside the bundle.

    `message_ids` is the exact set a purge is allowed to delete — not a range,
    so a message that failed to export can never be caught up in it.
    """
    return {
        'version': MANIFEST_VERSION,
        'guild_id': guild_id,
        'guild_name': transcript.guild_name,
        'channel_id': channel_id,
        'channel_name': transcript.channel_name,
        'generated_at': transcript.generated_at.isoformat(timespec='seconds'),
        'exported_by': exported_by,
        'exported_by_name': exported_by_name,
        'message_count': len(transcript.messages),
        'attachment_count': transcript.attachment_count,
        'attachment_bytes': transcript.attachment_bytes,
        'first_message_id': transcript.first_id,
        'last_message_id': transcript.last_id,
        'message_ids': transcript.message_ids,
    }


def read_manifest(bundle: Path) -> dict:
    """Read a bundle's manifest, or raise ArchiveError explaining why not.

    Everything a purge trusts comes through here, so every failure mode —
    missing bundle, not a zip, no manifest, bad JSON, wrong shape — has to be
    an explicit refusal rather than an exception the user cannot act on.
    """
    if not bundle.exists():
        raise ArchiveError(
            f'The backup `{bundle.name}` is gone, so there is nothing proving '
            f'those messages were saved. Nothing was deleted.'
        )
    try:
        with zipfile.ZipFile(bundle) as zf:
            raw = zf.read(MANIFEST_NAME)
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise ArchiveError(
            f'`{bundle.name}` could not be read as a backup ({exc}). '
            f'Nothing was deleted.'
        ) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ArchiveError(
            f'The manifest inside `{bundle.name}` is not valid JSON. '
            f'Nothing was deleted.'
        ) from exc
    ids = data.get('message_ids')
    if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
        raise ArchiveError(
            f'The manifest inside `{bundle.name}` has no usable message list. '
            f'Nothing was deleted.'
        )
    return data


# ---------------------------------------------------------------------------
# Export records (the audit trail)
# ---------------------------------------------------------------------------

def record_export(guild_id: int, channel_id: int, manifest: dict, bundle: Path) -> None:
    cfg = ArchiveConfig()
    guild = cfg.get(str(guild_id), {})
    guild[str(channel_id)] = {
        'channel_name': manifest['channel_name'],
        'bundle': bundle.name,
        'bundle_bytes': bundle.stat().st_size if bundle.exists() else 0,
        'generated_at': manifest['generated_at'],
        'exported_by': manifest['exported_by'],
        'exported_by_name': manifest['exported_by_name'],
        'message_count': manifest['message_count'],
        'attachment_count': manifest['attachment_count'],
        'first_message_id': manifest['first_message_id'],
        'last_message_id': manifest['last_message_id'],
        'purged_at': None,
        'purged_count': 0,
    }
    cfg.set(str(guild_id), guild)


def get_record(guild_id: int, channel_id: int) -> dict | None:
    return ArchiveConfig().get(str(guild_id), {}).get(str(channel_id))


def all_records(guild_id: int) -> dict:
    return ArchiveConfig().get(str(guild_id), {})


def mark_purged(guild_id: int, channel_id: int, deleted: int) -> None:
    cfg = ArchiveConfig()
    guild = cfg.get(str(guild_id), {})
    record = guild.get(str(channel_id))
    if not record:
        return
    record['purged_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    record['purged_count'] = deleted
    cfg.set(str(guild_id), guild)


def guild_dir(guild_id: int) -> Path:
    """Where this guild's bundles live. Created on resolve."""
    from utils.config import ARCHIVE_DIR
    path = ARCHIVE_DIR / str(guild_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
