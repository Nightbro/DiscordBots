import json
import pytest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from utils.intro_config import (
    canonicalize_days,
    clear_trigger,
    get_intro_file,
    get_user_intro,
    list_entries,
    parse_days,
    remove_schedule_entry,
    rename_entry,
    set_default_entry,
    set_schedule_entry,
    _file_for_today,
)


# ---------------------------------------------------------------------------
# parse_days
# ---------------------------------------------------------------------------

def test_parse_days_single():
    assert parse_days('MON') == frozenset({0})


def test_parse_days_multiple():
    assert parse_days('MON,FRI') == frozenset({0, 4})


def test_parse_days_range():
    assert parse_days('MON-FRI') == frozenset({0, 1, 2, 3, 4})


def test_parse_days_weekday_alias():
    assert parse_days('WEEKDAY') == frozenset({0, 1, 2, 3, 4})


def test_parse_days_weekend_alias():
    assert parse_days('WEEKEND') == frozenset({5, 6})


def test_parse_days_star():
    assert parse_days('*') == frozenset(range(7))


def test_parse_days_case_insensitive():
    assert parse_days('mon') == frozenset({0})


def test_parse_days_invalid_raises():
    with pytest.raises(ValueError):
        parse_days('BADDAY')


def test_parse_days_invalid_range_raises():
    with pytest.raises(ValueError):
        parse_days('FRI-MON')


def test_parse_days_empty_raises():
    with pytest.raises(ValueError):
        parse_days('')


# ---------------------------------------------------------------------------
# canonicalize_days
# ---------------------------------------------------------------------------

def test_canonicalize_sorted():
    result = canonicalize_days(frozenset({4, 0}))
    assert result == 'MON,FRI'


def test_canonicalize_single():
    assert canonicalize_days(frozenset({6})) == 'SUN'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config_file(tmp_path):
    return tmp_path / 'intro_config.json'


@pytest.fixture
def patch_config(config_file):
    from utils.persistence import IntroConfig

    class _TmpIntroConfig(IntroConfig):
        def __init__(self):
            self.path = config_file

    with patch('utils.intro_config.IntroConfig', _TmpIntroConfig):
        yield config_file


# ---------------------------------------------------------------------------
# _file_for_today
# ---------------------------------------------------------------------------

def test_file_for_today_schedule_wins(tmp_path):
    default_f = tmp_path / 'default.mp3'
    default_f.write_bytes(b'x')
    sched_f = tmp_path / 'sched.mp3'
    sched_f.write_bytes(b'x')
    entry = {
        'default': {'file': str(default_f), 'source': 'x'},
        'schedule': [{'days': 'MON', 'file': str(sched_f), 'source': 'y'}],
    }
    monday = date(2026, 5, 18)  # Monday
    with patch('utils.intro_config.date') as mock_date:
        mock_date.today.return_value = monday
        result = _file_for_today(entry)
    assert result == sched_f


def test_file_for_today_default_when_no_match(tmp_path):
    default_f = tmp_path / 'default.mp3'
    default_f.write_bytes(b'x')
    entry = {
        'default': {'file': str(default_f), 'source': 'x'},
        'schedule': [{'days': 'SUN', 'file': str(tmp_path / 'sun.mp3'), 'source': 'y'}],
    }
    monday = date(2026, 5, 18)  # Monday
    with patch('utils.intro_config.date') as mock_date:
        mock_date.today.return_value = monday
        result = _file_for_today(entry)
    assert result == default_f


def test_file_for_today_missing_file(tmp_path):
    entry = {'default': {'file': str(tmp_path / 'gone.mp3'), 'source': 'x'}}
    result = _file_for_today(entry)
    assert result is None


# ---------------------------------------------------------------------------
# set_default_entry / get_intro_file
# ---------------------------------------------------------------------------

def test_set_and_get_default_entry(patch_config, tmp_path):
    f = tmp_path / 'bot.mp3'
    f.write_bytes(b'audio')
    set_default_entry(1, 'bot', str(f), 'bot.mp3')
    result = get_intro_file(1, 'bot')
    assert result == f


def test_get_intro_file_missing_file(patch_config, tmp_path):
    missing = tmp_path / 'gone.mp3'
    set_default_entry(1, 'bot', str(missing), 'gone.mp3')
    assert get_intro_file(1, 'bot') is None


def test_get_intro_file_no_entry(patch_config):
    assert get_intro_file(999, 'bot') is None


def test_set_default_with_member_name(patch_config, tmp_path):
    f = tmp_path / 'user.mp3'
    f.write_bytes(b'x')
    set_default_entry(1, 'user_123', str(f), 'user.mp3', member_name='Alice')
    entries = list_entries(1)
    assert entries['user_123']['member_name'] == 'Alice'


# ---------------------------------------------------------------------------
# set_schedule_entry / remove_schedule_entry
# ---------------------------------------------------------------------------

def test_set_schedule_returns_canon(patch_config, tmp_path):
    f = tmp_path / 'sched.mp3'
    f.write_bytes(b'x')
    canon = set_schedule_entry(1, 'bot', 'MON', str(f), 'sched.mp3')
    assert canon == 'MON'


def test_set_schedule_replaces_existing(patch_config, tmp_path):
    f1 = tmp_path / 'a.mp3'
    f1.write_bytes(b'x')
    f2 = tmp_path / 'b.mp3'
    f2.write_bytes(b'x')
    set_schedule_entry(1, 'bot', 'MON', str(f1), 'a')
    set_schedule_entry(1, 'bot', 'MON', str(f2), 'b')
    entries = list_entries(1)
    schedule = entries['bot']['schedule']
    assert len(schedule) == 1
    assert schedule[0]['source'] == 'b'


def test_remove_schedule_entry_found(patch_config, tmp_path):
    f = tmp_path / 'sched.mp3'
    f.write_bytes(b'x')
    set_schedule_entry(1, 'bot', 'MON', str(f), 'sched.mp3')
    removed = remove_schedule_entry(1, 'bot', 'MON')
    assert removed is True
    entries = list_entries(1)
    assert entries.get('bot', {}).get('schedule', []) == []


def test_remove_schedule_entry_not_found(patch_config):
    removed = remove_schedule_entry(1, 'bot', 'FRI')
    assert removed is False


# ---------------------------------------------------------------------------
# clear_trigger
# ---------------------------------------------------------------------------

def test_clear_trigger_removes_entry(patch_config, tmp_path):
    f = tmp_path / 'bot.mp3'
    f.write_bytes(b'x')
    set_default_entry(1, 'bot', str(f), 'bot.mp3')
    entry = clear_trigger(1, 'bot')
    assert entry is not None
    assert list_entries(1) == {}


def test_clear_trigger_not_found(patch_config):
    result = clear_trigger(1, 'nonexistent')
    assert result is None


# ---------------------------------------------------------------------------
# get_user_intro — priority chain
# ---------------------------------------------------------------------------

def test_get_user_intro_per_member_wins(patch_config, tmp_path):
    user_f = tmp_path / 'user_123.mp3'
    user_f.write_bytes(b'x')
    server_f = tmp_path / 'server.mp3'
    server_f.write_bytes(b'x')
    set_default_entry(1, 'user_123', str(user_f), 'user_123.mp3')
    set_default_entry(1, 'user', str(server_f), 'server.mp3')
    result = get_user_intro(1, 123)
    assert result == user_f


def test_get_user_intro_falls_back_to_server(patch_config, tmp_path):
    server_f = tmp_path / 'server.mp3'
    server_f.write_bytes(b'x')
    set_default_entry(1, 'user', str(server_f), 'server.mp3')
    result = get_user_intro(1, 456)
    assert result == server_f


def test_get_user_intro_none_when_empty(patch_config):
    assert get_user_intro(1, 999) is None


# ---------------------------------------------------------------------------
# rename_entry
# ---------------------------------------------------------------------------

def test_rename_entry_success(patch_config, tmp_path):
    f = tmp_path / 'bot.mp3'
    f.write_bytes(b'x')
    set_default_entry(1, 'bot', str(f), 'original')
    ok = rename_entry(1, 'bot', 'My Bot Intro')
    assert ok is True
    entries = list_entries(1)
    assert entries['bot']['default']['source'] == 'My Bot Intro'


def test_rename_entry_not_found(patch_config):
    ok = rename_entry(1, 'nonexistent', 'New Name')
    assert ok is False


def test_rename_entry_no_default(patch_config, tmp_path):
    f = tmp_path / 'sched.mp3'
    f.write_bytes(b'x')
    set_schedule_entry(1, 'bot', 'MON', str(f), 'sched')
    ok = rename_entry(1, 'bot', 'New')
    assert ok is False


# ---------------------------------------------------------------------------
# list_entries
# ---------------------------------------------------------------------------

def test_list_entries_empty(patch_config):
    assert list_entries(1) == {}


def test_list_entries_multiple(patch_config, tmp_path):
    f = tmp_path / 'f.mp3'
    f.write_bytes(b'x')
    set_default_entry(1, 'bot', str(f), 'x')
    set_default_entry(1, 'user', str(f), 'y')
    entries = list_entries(1)
    assert 'bot' in entries
    assert 'user' in entries
