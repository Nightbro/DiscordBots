"""Unit tests for utils/soundboard_config.py"""
import json
import pytest

import utils.soundboard_config as sbc
from utils.soundboard_config import (
    load_soundboard_config, save_soundboard_config,
    get_sounds, get_sound, add_sound, remove_sound,
)

GUILD = 999


@pytest.fixture(autouse=True)
def patch_config_file(tmp_path, monkeypatch):
    cfg_file = tmp_path / 'soundboard_config.json'
    monkeypatch.setattr(sbc, 'SOUNDBOARD_CONFIG_FILE', cfg_file)


# ---------------------------------------------------------------------------
# load / save
# ---------------------------------------------------------------------------

def test_load_returns_empty_when_missing():
    assert load_soundboard_config() == {}


def test_save_and_reload(tmp_path, monkeypatch):
    cfg_file = tmp_path / 'sb.json'
    monkeypatch.setattr(sbc, 'SOUNDBOARD_CONFIG_FILE', cfg_file)
    data = {'111': {'boom': {'emoji': '💥', 'file': '/f.mp3', 'source': 'url'}}}
    save_soundboard_config(data)
    assert load_soundboard_config() == data


# ---------------------------------------------------------------------------
# get_sounds / get_sound
# ---------------------------------------------------------------------------

def test_get_sounds_empty_guild():
    assert get_sounds(GUILD) == {}


def test_get_sound_missing():
    assert get_sound(GUILD, 'nonexistent') is None


def test_get_sound_returns_entry():
    add_sound(GUILD, 'boom', '💥', '/boom.mp3', 'https://example.com')
    entry = get_sound(GUILD, 'boom')
    assert entry is not None
    assert entry['emoji'] == '💥'
    assert entry['file'] == '/boom.mp3'
    assert entry['source'] == 'https://example.com'


# ---------------------------------------------------------------------------
# add_sound
# ---------------------------------------------------------------------------

def test_add_sound_creates_entry():
    add_sound(GUILD, 'air_horn', '📯', '/air.mp3', 'air horn search')
    sounds = get_sounds(GUILD)
    assert 'air_horn' in sounds
    assert sounds['air_horn']['emoji'] == '📯'


def test_add_sound_overwrites_existing():
    add_sound(GUILD, 'sfx', '🔊', '/old.mp3', 'old source')
    add_sound(GUILD, 'sfx', '🎺', '/new.mp3', 'new source')
    entry = get_sound(GUILD, 'sfx')
    assert entry['emoji'] == '🎺'
    assert entry['file'] == '/new.mp3'


def test_add_sound_multiple_guilds():
    add_sound(1, 'ping', '🔔', '/ping.mp3', 'ping')
    add_sound(2, 'ping', '🔕', '/ping2.mp3', 'ping2')
    assert get_sound(1, 'ping')['emoji'] == '🔔'
    assert get_sound(2, 'ping')['emoji'] == '🔕'


# ---------------------------------------------------------------------------
# remove_sound
# ---------------------------------------------------------------------------

def test_remove_sound_returns_entry():
    add_sound(GUILD, 'bye', '👋', '/bye.mp3', 'bye')
    entry = remove_sound(GUILD, 'bye')
    assert entry is not None
    assert entry['emoji'] == '👋'
    assert get_sound(GUILD, 'bye') is None


def test_remove_sound_missing_returns_none():
    assert remove_sound(GUILD, 'ghost') is None


def test_remove_sound_persists_deletion():
    add_sound(GUILD, 'temp', '❄️', '/t.mp3', 't')
    remove_sound(GUILD, 'temp')
    # Reload from disk
    sounds = get_sounds(GUILD)
    assert 'temp' not in sounds
