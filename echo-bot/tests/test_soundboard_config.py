import pytest
from pathlib import Path
from unittest.mock import patch

from utils.soundboard_config import (
    add_sound,
    get_sound,
    get_sound_path,
    get_sounds,
    remove_sound,
    sound_exists,
)


@pytest.fixture()
def mock_cfg():
    """Patch SoundboardConfig with an in-memory dict store."""
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

    with patch('utils.soundboard_config.SoundboardConfig', return_value=_FakeCfg()):
        yield store


def test_add_and_get_sound(mock_cfg):
    add_sound('boom', 'boom.mp3', '💥')
    meta = get_sound('boom')
    assert meta == {'emoji': '💥', 'file': 'boom.mp3'}


def test_add_sound_default_emoji(mock_cfg):
    add_sound('airhorn', 'airhorn.mp3')
    meta = get_sound('airhorn')
    assert 'emoji' in meta
    assert meta['file'] == 'airhorn.mp3'


def test_get_sounds_returns_all(mock_cfg):
    add_sound('a', 'a.mp3', '🔊')
    add_sound('b', 'b.mp3', '💥')
    sounds = get_sounds()
    assert 'a' in sounds
    assert 'b' in sounds


def test_sound_exists(mock_cfg):
    assert sound_exists('boom') is False
    add_sound('boom', 'boom.mp3')
    assert sound_exists('boom') is True


def test_remove_sound_returns_true_when_existed(mock_cfg):
    add_sound('boom', 'boom.mp3')
    assert remove_sound('boom') is True


def test_remove_sound_returns_false_when_missing(mock_cfg):
    assert remove_sound('nonexistent') is False


def test_get_sound_path_returns_path_when_file_exists(mock_cfg, tmp_path):
    f = tmp_path / 'boom.mp3'
    f.write_bytes(b'')
    add_sound('boom', 'boom.mp3')
    with patch('utils.soundboard_config.SOUNDBOARD_DIR', tmp_path):
        path = get_sound_path('boom')
    assert path == f


def test_get_sound_path_returns_none_when_file_missing(mock_cfg, tmp_path):
    add_sound('boom', 'boom.mp3')
    with patch('utils.soundboard_config.SOUNDBOARD_DIR', tmp_path):
        path = get_sound_path('boom')
    assert path is None


def test_get_sound_path_returns_none_when_not_configured(mock_cfg):
    path = get_sound_path('nonexistent')
    assert path is None
