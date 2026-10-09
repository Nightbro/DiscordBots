import pytest
from unittest.mock import patch

from utils import library
from utils.library import LibraryError


@pytest.fixture(autouse=True)
def library_paths(tmp_path):
    """Isolate both the index file and the audio directory."""
    with patch('utils.library.LIBRARY_DIR', tmp_path / 'library'), \
         patch('utils.config.LIBRARY_CONFIG_FILE', tmp_path / 'library_config.json'):
        yield


def _add(guild_id: int, title: str, *, size: int = 1024, duration: int | None = 180) -> str:
    slug = library.slugify(title)
    path = library.guild_dir(guild_id) / f'{slug}.mp3'
    path.write_bytes(b'x' * size)
    return library.add_track(
        guild_id, title, path, duration=duration, added_by=1, added_by_name='Tester',
    )


# ---------------------------------------------------------------------------
# slugify / parse_index / format_duration
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('title,expected', [
    ('Halloween', 'halloween'),
    ('Thunder Beneath The Streets', 'thunder-beneath-the-streets'),
    ('Hällö Wörld!', 'hallo-world'),
    ('  spaced  out  ', 'spaced-out'),
    ('***', 'track'),
])
def test_slugify(title, expected):
    assert library.slugify(title) == expected


@pytest.mark.parametrize('query,expected', [
    ('#3', 3), ('# 3', 3), ('#1', 1), ('halloween', None), ('#0', None), ('#x', None), ('', None),
])
def test_parse_index(query, expected):
    assert library.parse_index(query) == expected


@pytest.mark.parametrize('secs,expected', [(None, '—'), (0, '—'), (62, '1:02'), (192, '3:12')])
def test_format_duration(secs, expected):
    assert library.format_duration(secs) == expected


# ---------------------------------------------------------------------------
# add / get / remove
# ---------------------------------------------------------------------------

def test_add_track_stores_metadata():
    slug = _add(1, 'Halloween', size=2048, duration=192)
    meta = library.get_track(1, slug)
    assert meta['title'] == 'Halloween'
    assert meta['file'] == 'halloween.mp3'
    assert meta['size'] == 2048
    assert meta['duration'] == 192
    assert meta['added_by_name'] == 'Tester'
    assert meta['plays'] == 0


def test_libraries_are_per_guild():
    _add(1, 'Mine')
    _add(2, 'Theirs')
    assert [m['title'] for _, m in library.track_list(1)] == ['Mine']
    assert [m['title'] for _, m in library.track_list(2)] == ['Theirs']
    assert library.find(1, 'Theirs') is None


def test_add_track_rejects_duplicate_name():
    _add(1, 'Halloween')
    with pytest.raises(LibraryError, match='name_taken'):
        _add(1, 'halloween')


def test_remove_track_deletes_file():
    slug = _add(1, 'Halloween')
    path = library.track_path(1, slug)
    assert library.remove_track(1, slug) is True
    assert not path.exists()
    assert library.get_track(1, slug) is None
    assert library.remove_track(1, slug) is False


def test_rename_track_keeps_file_and_moves_key():
    slug = _add(1, 'Old Name')
    new_slug = library.rename_track(1, slug, 'New Name')
    assert new_slug == 'new-name'
    assert library.get_track(1, slug) is None
    meta = library.get_track(1, new_slug)
    assert meta['title'] == 'New Name'
    assert meta['file'] == 'old-name.mp3'
    assert library.track_path(1, new_slug).exists()


def test_rename_rejects_existing_name():
    slug = _add(1, 'One')
    _add(1, 'Two')
    with pytest.raises(LibraryError, match='name_taken'):
        library.rename_track(1, slug, 'Two')


def test_rename_missing_track_raises():
    with pytest.raises(LibraryError, match='not_found'):
        library.rename_track(1, 'nope', 'Something')


def test_bump_plays():
    slug = _add(1, 'Halloween')
    library.bump_plays(1, slug)
    library.bump_plays(1, slug)
    assert library.get_track(1, slug)['plays'] == 2
    library.bump_plays(1, 'missing')  # must not raise


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def test_track_list_sorted_by_title():
    _add(1, 'Zebra')
    _add(1, 'apple')
    _add(1, 'Mango')
    assert [m['title'] for _, m in library.track_list(1)] == ['apple', 'Mango', 'Zebra']


def test_find_exact_beats_partial():
    _add(1, 'Night')
    _add(1, 'Night Rider')
    slug, meta = library.find(1, 'night')
    assert meta['title'] == 'Night'


def test_find_partial_match():
    _add(1, 'Thunder Beneath The Streets')
    slug, meta = library.find(1, 'thunder')
    assert meta['title'] == 'Thunder Beneath The Streets'


def test_find_all_returns_every_match():
    _add(1, 'Night')
    _add(1, 'Night Rider')
    assert len(library.find_all(1, 'night')) == 2


def test_find_returns_none_for_unknown():
    _add(1, 'Halloween')
    assert library.find(1, 'nothing') is None
    assert library.find(1, '') is None


def test_resolve_by_index():
    _add(1, 'apple')
    _add(1, 'banana')
    assert library.resolve(1, '#2')[1]['title'] == 'banana'
    assert library.resolve(1, '#9') is None


def test_is_exact_match():
    slug = _add(1, 'Halloween')
    meta = library.get_track(1, slug)
    assert library.is_exact_match('halloween', slug, meta) is True
    assert library.is_exact_match('HALLOWEEN', slug, meta) is True
    assert library.is_exact_match('hallo', slug, meta) is False


def test_to_track_builds_playable_track():
    slug = _add(1, 'Halloween', duration=192)
    track = library.to_track(1, slug)
    assert track.title == 'Halloween'
    assert track.file_path.exists()
    assert track.duration == 192
    assert track.source_id == 'lib:halloween'


def test_to_track_none_when_file_deleted():
    slug = _add(1, 'Halloween')
    library.track_path(1, slug).unlink()
    assert library.to_track(1, slug) is None
    assert library.track_path(1, slug) is None


# ---------------------------------------------------------------------------
# Quota
# ---------------------------------------------------------------------------

def test_check_quota_allows_within_limits():
    _add(1, 'One', size=1024)
    library.check_quota(1, 1024)  # must not raise


def test_check_quota_rejects_track_count():
    with patch('utils.library.LIBRARY_MAX_TRACKS', 2):
        _add(1, 'One')
        _add(1, 'Two')
        with pytest.raises(LibraryError, match='track_limit:2'):
            library.check_quota(1, 10)


def test_check_quota_rejects_total_size():
    with patch('utils.library.LIBRARY_MAX_TOTAL_MB', 1):
        _add(1, 'One', size=900 * 1024)
        with pytest.raises(LibraryError, match='size_limit:1'):
            library.check_quota(1, 200 * 1024)


def test_quota_is_counted_per_guild():
    with patch('utils.library.LIBRARY_MAX_TRACKS', 1):
        _add(1, 'One')
        library.check_quota(2, 10)  # other guild unaffected


def test_total_size():
    _add(1, 'One', size=1000)
    _add(1, 'Two', size=2000)
    assert library.total_size(1) == 3000


# ---------------------------------------------------------------------------
# probe_duration
# ---------------------------------------------------------------------------

async def test_probe_duration_returns_none_when_ffprobe_missing(tmp_path):
    path = tmp_path / 'x.mp3'
    path.write_bytes(b'')
    with patch('asyncio.create_subprocess_exec', side_effect=FileNotFoundError):
        assert await library.probe_duration(path) is None
