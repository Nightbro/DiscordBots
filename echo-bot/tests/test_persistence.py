import json
import pytest
from pathlib import Path

from utils.persistence import BaseConfig, IntroConfig, SoundboardConfig, PlaylistConfig


class _Cfg(BaseConfig):
    def __init__(self, path: Path) -> None:
        self.path = path


def test_load_missing_file_returns_empty(tmp_path):
    cfg = _Cfg(tmp_path / 'missing.json')
    assert cfg.load() == {}


def test_save_and_load_roundtrip(tmp_path):
    cfg = _Cfg(tmp_path / 'data.json')
    data = {'key': 'value', 'num': 42}
    cfg.save(data)
    assert cfg.load() == data


def test_save_writes_valid_json(tmp_path):
    p = tmp_path / 'data.json'
    cfg = _Cfg(p)
    cfg.save({'a': 1})
    assert json.loads(p.read_text(encoding='utf-8')) == {'a': 1}


def test_get_existing_key(tmp_path):
    cfg = _Cfg(tmp_path / 'data.json')
    cfg.save({'x': 'hello'})
    assert cfg.get('x') == 'hello'


def test_get_missing_key_returns_default(tmp_path):
    cfg = _Cfg(tmp_path / 'data.json')
    assert cfg.get('missing') is None
    assert cfg.get('missing', 'fallback') == 'fallback'


def test_set_creates_key(tmp_path):
    cfg = _Cfg(tmp_path / 'data.json')
    cfg.set('name', 'Echo')
    assert cfg.get('name') == 'Echo'


def test_set_overwrites_existing_key(tmp_path):
    cfg = _Cfg(tmp_path / 'data.json')
    cfg.save({'n': 1})
    cfg.set('n', 99)
    assert cfg.get('n') == 99


def test_set_preserves_other_keys(tmp_path):
    cfg = _Cfg(tmp_path / 'data.json')
    cfg.save({'a': 1, 'b': 2})
    cfg.set('a', 10)
    assert cfg.get('b') == 2


def test_delete_existing_key(tmp_path):
    cfg = _Cfg(tmp_path / 'data.json')
    cfg.save({'x': 1, 'y': 2})
    result = cfg.delete('x')
    assert result is True
    assert cfg.get('x') is None
    assert cfg.get('y') == 2


def test_delete_missing_key_returns_false(tmp_path):
    cfg = _Cfg(tmp_path / 'data.json')
    assert cfg.delete('nonexistent') is False


def test_all_returns_full_dict(tmp_path):
    cfg = _Cfg(tmp_path / 'data.json')
    data = {'a': 1, 'b': [1, 2, 3]}
    cfg.save(data)
    assert cfg.all() == data


def test_unicode_roundtrip(tmp_path):
    cfg = _Cfg(tmp_path / 'data.json')
    cfg.save({'emoji': '🎵', 'text': 'héllo'})
    assert cfg.get('emoji') == '🎵'
    assert cfg.get('text') == 'héllo'


def test_intro_config_path_under_data():
    cfg = IntroConfig()
    assert cfg.path.name == 'intro_config.json'
    assert 'data' in cfg.path.parts


def test_soundboard_config_path_under_data():
    cfg = SoundboardConfig()
    assert cfg.path.name == 'soundboard_config.json'
    assert 'data' in cfg.path.parts


def test_playlist_config_path_under_data():
    cfg = PlaylistConfig()
    assert cfg.path.name == 'playlists.json'
    assert 'data' in cfg.path.parts
