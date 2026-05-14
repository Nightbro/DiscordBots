import datetime
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from utils.intro_config import (
    parse_days,
    canonicalize_days,
    set_default_entry,
    set_schedule_entry,
    remove_schedule_entry,
    set_override_entry,
    remove_override_entry,
    clear_trigger,
    get_intro_file,
    get_auto_join,
    set_auto_join,
    list_entries,
    get_user_entry,
)


# ---------------------------------------------------------------------------
# parse_days
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('text,expected', [
    ('mon', ['mon']),
    ('monday', ['mon']),
    ('Mon', ['mon']),
    ('mon,fri', ['mon', 'fri']),
    ('monday, friday', ['mon', 'fri']),
    ('', []),
    ('invalid', []),
])
def test_parse_days(text, expected):
    assert parse_days(text) == expected


# ---------------------------------------------------------------------------
# canonicalize_days
# ---------------------------------------------------------------------------

def test_canonicalize_days_sorted():
    assert canonicalize_days(['fri', 'mon', 'wed']) == ['mon', 'wed', 'fri']


def test_canonicalize_days_deduped():
    assert canonicalize_days(['mon', 'mon', 'tue']) == ['mon', 'tue']


def test_canonicalize_days_all():
    assert canonicalize_days(['sun', 'sat', 'fri', 'thu', 'wed', 'tue', 'mon']) == \
        ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']


# ---------------------------------------------------------------------------
# set/get/clear entry helpers (backed by in-memory mock)
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_cfg():
    """Patch IntroConfig with an in-memory dict store."""
    store: dict = {}

    class _FakeCfg:
        def get(self, key, default=None):
            return store.get(key, default)

        def set(self, key, value):
            store[key] = value

        def delete(self, key):
            if key in store:
                del store[key]
                return True
            return False

        def all(self):
            return dict(store)

    with patch('utils.intro_config.IntroConfig', return_value=_FakeCfg()):
        yield store


def test_set_and_get_default_entry(mock_cfg):
    set_default_entry(1, 'intro.mp3')
    assert get_user_entry(1).get('default') == 'intro.mp3'


def test_set_schedule_entry(mock_cfg):
    set_schedule_entry(1, ['mon', 'fri'], 'weekday.mp3')
    entry = get_user_entry(1)
    assert entry['schedule']['mon'] == 'weekday.mp3'
    assert entry['schedule']['fri'] == 'weekday.mp3'


def test_remove_schedule_entry_returns_removed(mock_cfg):
    set_schedule_entry(1, ['mon', 'fri'], 'f.mp3')
    removed = remove_schedule_entry(1, ['mon', 'sat'])
    assert removed == ['mon']
    entry = get_user_entry(1)
    assert 'mon' not in entry.get('schedule', {})
    assert 'fri' in entry.get('schedule', {})


def test_set_override_entry(mock_cfg):
    set_override_entry(1, '2024-12-25', 'xmas.mp3')
    entry = get_user_entry(1)
    assert entry['overrides']['2024-12-25'] == 'xmas.mp3'


def test_remove_override_entry(mock_cfg):
    set_override_entry(1, '2024-12-25', 'xmas.mp3')
    assert remove_override_entry(1, '2024-12-25') is True
    assert remove_override_entry(1, '2024-12-25') is False


def test_clear_trigger(mock_cfg):
    set_default_entry(1, 'f.mp3')
    assert clear_trigger(1) is True
    assert clear_trigger(1) is False


def test_auto_join(mock_cfg):
    assert get_auto_join(1) is False
    set_auto_join(1, True)
    assert get_auto_join(1) is True
    set_auto_join(1, False)
    assert get_auto_join(1) is False


def test_list_entries(mock_cfg):
    set_default_entry(1, 'a.mp3')
    set_default_entry(2, 'b.mp3')
    all_entries = list_entries()
    assert '1' in all_entries
    assert '2' in all_entries


# ---------------------------------------------------------------------------
# get_intro_file — priority logic
# ---------------------------------------------------------------------------

@pytest.fixture()
def intro_fs(tmp_path, mock_cfg):
    """Set up a real temp filesystem for user intro files."""
    uid = 42
    d = tmp_path / str(uid)
    d.mkdir()

    default_file = d / 'default.mp3'
    default_file.write_bytes(b'')
    schedule_file = d / 'weekday.mp3'
    schedule_file.write_bytes(b'')
    override_file = d / 'xmas.mp3'
    override_file.write_bytes(b'')

    with patch('utils.intro_config.user_dir', return_value=d):
        with patch('utils.intro_config.INTRO_SOUNDS_DIR', tmp_path):
            set_default_entry(uid, 'default.mp3')
            set_schedule_entry(uid, ['mon'], 'weekday.mp3')
            set_override_entry(uid, '2024-12-25', 'xmas.mp3')
            yield uid, d


def test_get_intro_file_override_takes_priority(intro_fs):
    uid, d = intro_fs
    date = datetime.date(2024, 12, 25)  # Wednesday
    path = get_intro_file(uid, today=date)
    assert path is not None
    assert path.name == 'xmas.mp3'


def test_get_intro_file_schedule_fallback(intro_fs):
    uid, d = intro_fs
    monday = datetime.date(2024, 12, 23)  # A monday
    path = get_intro_file(uid, today=monday)
    assert path is not None
    assert path.name == 'weekday.mp3'


def test_get_intro_file_default_fallback(intro_fs):
    uid, d = intro_fs
    tuesday = datetime.date(2024, 12, 24)  # Tuesday — no schedule
    path = get_intro_file(uid, today=tuesday)
    assert path is not None
    assert path.name == 'default.mp3'


def test_get_intro_file_none_when_no_entry(mock_cfg):
    path = get_intro_file(9999)
    assert path is None


def test_get_intro_file_none_when_file_missing(tmp_path, mock_cfg):
    uid = 77
    d = tmp_path / str(uid)
    d.mkdir()
    # Set a default but don't create the file
    with patch('utils.intro_config.user_dir', return_value=d):
        set_default_entry(uid, 'missing.mp3')
        path = get_intro_file(uid)
    assert path is None
