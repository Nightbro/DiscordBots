"""The JSON store, and the atomic-write guarantee Chronicler relies on."""

import json

import pytest

from utils.persistence import BaseConfig


class _Store(BaseConfig):
    def __init__(self, path):
        self.path = path


@pytest.fixture
def store(tmp_path):
    return _Store(tmp_path / 'store.json')


# ---------------------------------------------------------------------------
# Basic round trip
# ---------------------------------------------------------------------------

def test_missing_file_loads_as_empty(store):
    assert store.load() == {}


def test_set_and_get(store):
    store.set('a', 1)
    assert store.get('a') == 1


def test_get_default_for_missing_key(store):
    assert store.get('nope', 'fallback') == 'fallback'


def test_delete_reports_whether_it_existed(store):
    store.set('a', 1)
    assert store.delete('a') is True
    assert store.delete('a') is False


def test_all_returns_the_whole_document(store):
    store.set('a', 1)
    store.set('b', 2)
    assert store.all() == {'a': 1, 'b': 2}


def test_save_creates_missing_parent_directories(tmp_path):
    nested = _Store(tmp_path / 'deep' / 'deeper' / 'store.json')
    nested.set('a', 1)
    assert nested.get('a') == 1


def test_unicode_survives_the_round_trip(store):
    store.set('name', 'Mršavi Vuk — ночь')
    assert store.get('name') == 'Mršavi Vuk — ночь'


# ---------------------------------------------------------------------------
# Corruption and atomicity
# ---------------------------------------------------------------------------

def test_corrupt_file_falls_back_to_empty(store):
    store.path.write_text('{ this is not json', encoding='utf-8')
    assert store.load() == {}


def test_successful_save_leaves_no_temp_file(store):
    store.set('a', 1)
    leftovers = list(store.path.parent.glob('*.tmp'))
    assert leftovers == []


def test_failed_save_leaves_no_temp_file(store):
    store.set('a', 1)
    with pytest.raises(TypeError):
        store.save({'bad': object()})  # not JSON-serializable
    assert list(store.path.parent.glob('*.tmp')) == []


def test_failed_save_keeps_the_previous_contents(store):
    """A write that blows up must not truncate what was already there."""
    store.set('a', 1)
    with pytest.raises(TypeError):
        store.save({'bad': object()})
    assert json.loads(store.path.read_text(encoding='utf-8')) == {'a': 1}


def test_save_replaces_rather_than_appends(store):
    store.save({'a': 1})
    store.save({'b': 2})
    assert store.load() == {'b': 2}
