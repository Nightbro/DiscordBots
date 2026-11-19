"""The archive domain model, the manifest, and the export record."""

import json
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from utils import archive
from utils.archive import (
    ArchiveError,
    ArchivedAttachment,
    ArchivedMessage,
    RangeSpec,
    Transcript,
)

CHANNEL_ID = 555000111
WHEN = datetime(2026, 11, 19, 14, 30, tzinfo=timezone.utc)


def _attachment(filename='shot.png', size=1024, message_id=900001, index=0):
    return ArchivedAttachment(
        filename=filename,
        stored_as=archive.stored_name(message_id, index, filename),
        size=size,
    )


def _message(message_id=900001, content='hello', attachments=None):
    return ArchivedMessage(
        id=message_id,
        author_id=42,
        author_name='Ivan',
        created_at=WHEN,
        content=content,
        attachments=attachments or [],
    )


def _transcript(messages=None):
    return Transcript(
        guild_name='The Table',
        channel_name='general',
        messages=messages if messages is not None else [_message()],
        generated_at=WHEN,
    )


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('raw,expected', [
    ('general', 'general'),
    ('Général #1!', 'general-1'),
    ('  spaced  out  ', 'spaced-out'),
    ('ночь', 'channel'),        # nothing survives the ASCII fold
    ('', 'channel'),
    ('---', 'channel'),
])
def test_safe_name(raw, expected):
    assert archive.safe_name(raw) == expected


@pytest.mark.parametrize('filename,expected', [
    ('a.png', True), ('a.JPG', True), ('a.jpeg', True), ('a.gif', True),
    ('a.webp', True), ('a.pdf', False), ('a.mp3', False), ('noext', False),
])
def test_is_image(filename, expected):
    assert archive.is_image(filename) is expected


def test_stored_name_is_unique_per_message_and_index():
    first = archive.stored_name(900001, 0, 'photo.png')
    second = archive.stored_name(900001, 1, 'photo.png')
    other = archive.stored_name(900002, 0, 'photo.png')
    assert len({first, second, other}) == 3
    assert first.endswith('.png')


def test_stored_name_keeps_the_extension_and_sanitises_the_stem():
    assert archive.stored_name(1, 0, 'My Holiday!.JPEG') == '1-0-my-holiday.jpeg'


def test_stored_name_truncates_a_long_stem():
    name = archive.stored_name(1, 0, f'{"x" * 200}.png')
    assert len(name) < 80
    assert name.endswith('.png')


def test_bundle_name_carries_channel_and_timestamp():
    assert archive.bundle_name('General Chat', WHEN) == 'general-chat-20261119-143000.zip'


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def test_attachment_routes_images_and_files_to_separate_folders():
    image = _attachment('shot.png')
    doc = _attachment('notes.pdf')
    assert image.path_in_bundle.startswith(f'{archive.IMAGES_DIR}/')
    assert doc.path_in_bundle.startswith(f'{archive.FILES_DIR}/')


def test_message_splits_images_from_other_files():
    message = _message(attachments=[_attachment('a.png'), _attachment('b.zip')])
    assert [a.filename for a in message.images] == ['a.png']
    assert [a.filename for a in message.files] == ['b.zip']


def test_transcript_totals():
    messages = [
        _message(900001, attachments=[_attachment('a.png', size=100)]),
        _message(900002, attachments=[_attachment('b.pdf', size=200)]),
        _message(900003),
    ]
    t = _transcript(messages)
    assert t.message_ids == [900001, 900002, 900003]
    assert (t.first_id, t.last_id) == (900001, 900003)
    assert t.attachment_count == 2
    assert t.attachment_bytes == 300


def test_empty_transcript_has_no_bounds():
    t = _transcript([])
    assert t.first_id is None and t.last_id is None
    assert t.message_ids == []


def test_range_spec_describes_itself():
    assert 'last 500' in RangeSpec(limit=500).describe()
    assert '111 to 222' in RangeSpec(start_id=111, end_id=222).describe()
    assert 'onwards' in RangeSpec(start_id=111).describe()


# ---------------------------------------------------------------------------
# Limits — refusals must happen before anything downloads
# ---------------------------------------------------------------------------

def test_message_count_within_limit_is_fine():
    archive.check_message_count(archive.max_messages())


def test_message_count_over_limit_is_refused():
    with pytest.raises(ArchiveError, match='the limit is'):
        archive.check_message_count(archive.max_messages() + 1)


def test_attachment_bytes_within_limit_is_fine():
    archive.check_attachment_bytes(archive.max_bundle_bytes())


def test_attachment_bytes_over_limit_is_refused():
    with pytest.raises(ArchiveError, match='MB'):
        archive.check_attachment_bytes(archive.max_bundle_bytes() + 1)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def _manifest(t=None):
    return archive.build_manifest(
        t or _transcript(),
        guild_id=123,
        channel_id=CHANNEL_ID,
        exported_by=42,
        exported_by_name='Ivan',
    )


def test_manifest_lists_every_message_id():
    t = _transcript([_message(1001), _message(1002), _message(1003)])
    manifest = _manifest(t)
    assert manifest['message_ids'] == [1001, 1002, 1003]
    assert manifest['message_count'] == 3
    assert manifest['first_message_id'] == 1001
    assert manifest['last_message_id'] == 1003


def test_manifest_records_who_and_when():
    manifest = _manifest()
    assert manifest['exported_by'] == 42
    assert manifest['exported_by_name'] == 'Ivan'
    assert manifest['generated_at'].startswith('2026-11-19')
    assert manifest['version'] == archive.MANIFEST_VERSION


def _bundle(tmp_path, manifest=None, name='bundle.zip'):
    path = tmp_path / name
    with zipfile.ZipFile(path, 'w') as zf:
        if manifest is not None:
            zf.writestr(archive.MANIFEST_NAME, json.dumps(manifest))
    return path


def test_manifest_round_trips_through_the_bundle(tmp_path):
    written = _manifest()
    assert archive.read_manifest(_bundle(tmp_path, written)) == written


def test_reading_a_missing_bundle_refuses(tmp_path):
    with pytest.raises(ArchiveError, match='is gone'):
        archive.read_manifest(tmp_path / 'nope.zip')


def test_reading_a_non_zip_refuses(tmp_path):
    path = tmp_path / 'broken.zip'
    path.write_text('definitely not a zip', encoding='utf-8')
    with pytest.raises(ArchiveError, match='could not be read'):
        archive.read_manifest(path)


def test_bundle_without_a_manifest_refuses(tmp_path):
    with pytest.raises(ArchiveError, match='could not be read'):
        archive.read_manifest(_bundle(tmp_path, manifest=None))


def test_bundle_with_unparseable_manifest_refuses(tmp_path):
    path = tmp_path / 'bad.zip'
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr(archive.MANIFEST_NAME, '{ not json')
    with pytest.raises(ArchiveError, match='not valid JSON'):
        archive.read_manifest(path)


@pytest.mark.parametrize('ids', [None, 'all of them', [1, 'two'], {}])
def test_manifest_without_a_usable_id_list_refuses(tmp_path, ids):
    """Deletion reads its target list from here, so a bad list must never pass."""
    with pytest.raises(ArchiveError, match='no usable message list'):
        archive.read_manifest(_bundle(tmp_path, {'message_ids': ids}))


def test_every_refusal_says_nothing_was_deleted(tmp_path):
    """The manifest reader is the purge interlock — its refusals must reassure."""
    with pytest.raises(ArchiveError, match='Nothing was deleted'):
        archive.read_manifest(_bundle(tmp_path, {'message_ids': None}))


# ---------------------------------------------------------------------------
# Export records
# ---------------------------------------------------------------------------

def test_record_is_stored_and_read_back(tmp_path, guild_id):
    bundle = _bundle(tmp_path, _manifest())
    archive.record_export(guild_id, CHANNEL_ID, _manifest(), bundle)
    record = archive.get_record(guild_id, CHANNEL_ID)
    assert record['channel_name'] == 'general'
    assert record['bundle'] == 'bundle.zip'
    assert record['message_count'] == 1
    assert record['purged_at'] is None


def test_records_are_per_guild(tmp_path, guild_id):
    archive.record_export(guild_id, CHANNEL_ID, _manifest(), _bundle(tmp_path, _manifest()))
    assert archive.get_record(999, CHANNEL_ID) is None
    assert archive.all_records(999) == {}


def test_a_second_export_replaces_the_record(tmp_path, guild_id):
    bundle = _bundle(tmp_path, _manifest())
    archive.record_export(guild_id, CHANNEL_ID, _manifest(), bundle)
    newer = _manifest(_transcript([_message(1), _message(2)]))
    archive.record_export(guild_id, CHANNEL_ID, newer, bundle)
    assert archive.get_record(guild_id, CHANNEL_ID)['message_count'] == 2
    assert len(archive.all_records(guild_id)) == 1


def test_mark_purged_updates_the_record(tmp_path, guild_id):
    archive.record_export(guild_id, CHANNEL_ID, _manifest(), _bundle(tmp_path, _manifest()))
    archive.mark_purged(guild_id, CHANNEL_ID, 17)
    record = archive.get_record(guild_id, CHANNEL_ID)
    assert record['purged_count'] == 17
    assert record['purged_at'] is not None


def test_mark_purged_on_an_unknown_channel_is_a_no_op(guild_id):
    archive.mark_purged(guild_id, 404, 5)
    assert archive.get_record(guild_id, 404) is None


# ---------------------------------------------------------------------------
# Deletion arithmetic
# ---------------------------------------------------------------------------

def _id_at(moment: datetime) -> int:
    """The snowflake a message posted at `moment` would carry."""
    return int(moment.timestamp() * 1000 - archive.DISCORD_EPOCH_MS) << 22


def test_snowflake_zero_is_the_discord_epoch():
    assert archive.snowflake_time(0) == datetime(2015, 1, 1, tzinfo=timezone.utc)


def test_snowflake_time_round_trips():
    moment = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
    assert abs((archive.snowflake_time(_id_at(moment)) - moment).total_seconds()) < 1


def test_split_by_age_keeps_recent_messages_for_bulk_delete():
    now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
    recent = _id_at(now - timedelta(days=1))
    recent_ids, old_ids = archive.split_by_age([recent], now=now)
    assert recent_ids == [recent]
    assert old_ids == []


def test_split_by_age_sends_old_messages_down_the_slow_path():
    now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
    old = _id_at(now - timedelta(days=30))
    recent_ids, old_ids = archive.split_by_age([old], now=now)
    assert recent_ids == []
    assert old_ids == [old]


def test_split_by_age_puts_the_boundary_at_fourteen_days():
    """Discord's bulk endpoint refuses anything older, so the split must match."""
    now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
    just_inside = _id_at(now - timedelta(days=13, hours=23))
    just_outside = _id_at(now - timedelta(days=14, hours=1))
    recent_ids, old_ids = archive.split_by_age([just_inside, just_outside], now=now)
    assert recent_ids == [just_inside]
    assert old_ids == [just_outside]


def test_split_by_age_preserves_order_within_each_group():
    now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
    ids = [
        _id_at(now - timedelta(days=1)),
        _id_at(now - timedelta(days=40)),
        _id_at(now - timedelta(days=2)),
        _id_at(now - timedelta(days=30)),
    ]
    recent_ids, old_ids = archive.split_by_age(ids, now=now)
    assert recent_ids == [ids[0], ids[2]]
    assert old_ids == [ids[1], ids[3]]


def test_split_by_age_of_nothing():
    assert archive.split_by_age([]) == ([], [])


def test_chunked_respects_the_bulk_limit():
    ids = list(range(250))
    batches = archive.chunked(ids)
    assert [len(b) for b in batches] == [100, 100, 50]
    assert [i for b in batches for i in b] == ids


def test_chunked_on_an_exact_multiple():
    assert [len(b) for b in archive.chunked(list(range(200)))] == [100, 100]


def test_chunked_of_nothing():
    assert archive.chunked([]) == []


def test_chunked_never_exceeds_discords_maximum():
    for batch in archive.chunked(list(range(1000))):
        assert len(batch) <= archive.BULK_DELETE_CHUNK


def test_chunked_rejects_a_nonsense_size():
    with pytest.raises(ValueError):
        archive.chunked([1, 2, 3], size=0)


def test_guild_dir_is_created_under_the_archive_dir(guild_id):
    path = archive.guild_dir(guild_id)
    assert path.exists()
    assert path.name == str(guild_id)
