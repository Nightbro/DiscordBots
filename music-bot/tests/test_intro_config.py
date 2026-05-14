"""Unit tests for utils/intro_config.py."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest


class TestLoadSaveRoundtrip:
    def test_load_returns_empty_when_no_file(self, tmp_path):
        with patch("utils.intro_config.INTRO_CONFIG_FILE", tmp_path / "missing.json"):
            from utils.intro_config import load_intro_config
            assert load_intro_config() == {}

    def test_roundtrip(self, tmp_path):
        cfg_file = tmp_path / "intro_config.json"
        data = {"123": {"bot": {"file": "/some/path.mp3", "source": "test.mp3"}}}

        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg_file):
            from utils.intro_config import load_intro_config, save_intro_config
            save_intro_config(data)
            assert load_intro_config() == data

    def test_save_creates_file(self, tmp_path):
        cfg_file = tmp_path / "intro_config.json"
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg_file):
            from utils.intro_config import save_intro_config
            save_intro_config({"x": 1})
            assert cfg_file.exists()


# ---------------------------------------------------------------------------
# parse_days / canonicalize_days
# ---------------------------------------------------------------------------

class TestParseDays:
    def _call(self, pattern):
        from utils.intro_config import parse_days
        return parse_days(pattern)

    def test_single_day(self):
        assert self._call('MON') == frozenset({0})
        assert self._call('SUN') == frozenset({6})

    def test_case_insensitive(self):
        assert self._call('mon') == frozenset({0})
        assert self._call('Sat') == frozenset({5})

    def test_comma_list(self):
        assert self._call('SAT,SUN') == frozenset({5, 6})
        assert self._call('MON,WED,FRI') == frozenset({0, 2, 4})

    def test_range(self):
        assert self._call('MON-FRI') == frozenset({0, 1, 2, 3, 4})
        assert self._call('WED-FRI') == frozenset({2, 3, 4})

    def test_weekday_alias(self):
        assert self._call('WEEKDAY') == frozenset({0, 1, 2, 3, 4})

    def test_weekend_alias(self):
        assert self._call('WEEKEND') == frozenset({5, 6})

    def test_wildcard(self):
        assert self._call('*') == frozenset(range(7))

    def test_invalid_day_raises(self):
        from utils.intro_config import parse_days
        with pytest.raises(ValueError, match='Unknown day'):
            parse_days('BLAH')

    def test_invalid_range_raises(self):
        from utils.intro_config import parse_days
        with pytest.raises(ValueError):
            parse_days('FRI-MON')  # high→low not allowed

    def test_invalid_range_names_raises(self):
        from utils.intro_config import parse_days
        with pytest.raises(ValueError):
            parse_days('MON-BLAH')

    def test_whitespace_trimmed(self):
        assert self._call('  SAT , SUN  ') == frozenset({5, 6})


class TestCanonicalizeDays:
    def test_sorted_output(self):
        from utils.intro_config import canonicalize_days
        assert canonicalize_days(frozenset({5, 6})) == 'SAT,SUN'
        assert canonicalize_days(frozenset({0, 2, 4})) == 'MON,WED,FRI'

    def test_single_day(self):
        from utils.intro_config import canonicalize_days
        assert canonicalize_days(frozenset({0})) == 'MON'

    def test_full_week(self):
        from utils.intro_config import canonicalize_days
        result = canonicalize_days(frozenset(range(7)))
        assert result == 'MON,TUE,WED,THU,FRI,SAT,SUN'


# ---------------------------------------------------------------------------
# _file_for_today (tested via get_intro_file with mocked date)
# ---------------------------------------------------------------------------

class TestFileForToday:
    def _write_cfg(self, tmp_path, data):
        f = tmp_path / "config.json"
        f.write_text(json.dumps(data))
        return f

    def test_flat_format_returns_file(self, tmp_path):
        intro = tmp_path / "intro.mp3"
        intro.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {"99": {"bot": {"file": str(intro), "source": "x"}}})
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            with patch("utils.intro_config._INTRO_FILE", tmp_path / "nope.mp3"):
                from utils.intro_config import get_intro_file
                assert get_intro_file(99, "bot") == intro

    def test_schedule_match_returns_override(self, tmp_path):
        default_file  = tmp_path / "default.mp3"
        weekend_file  = tmp_path / "weekend.mp3"
        default_file.write_bytes(b"fake")
        weekend_file.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {
                "default":  {"file": str(default_file), "source": "def"},
                "schedule": [{"days": "SAT,SUN", "file": str(weekend_file), "source": "wknd"}],
            }}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            with patch("utils.intro_config._INTRO_FILE", tmp_path / "nope.mp3"):
                with patch("utils.intro_config.date") as mock_date:
                    mock_date.today.return_value.weekday.return_value = 5  # Saturday
                    from utils.intro_config import get_intro_file
                    assert get_intro_file(99, "bot") == weekend_file

    def test_schedule_no_match_falls_back_to_default(self, tmp_path):
        default_file = tmp_path / "default.mp3"
        weekend_file = tmp_path / "weekend.mp3"
        default_file.write_bytes(b"fake")
        weekend_file.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {
                "default":  {"file": str(default_file), "source": "def"},
                "schedule": [{"days": "SAT,SUN", "file": str(weekend_file), "source": "wknd"}],
            }}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            with patch("utils.intro_config._INTRO_FILE", tmp_path / "nope.mp3"):
                with patch("utils.intro_config.date") as mock_date:
                    mock_date.today.return_value.weekday.return_value = 0  # Monday
                    from utils.intro_config import get_intro_file
                    assert get_intro_file(99, "bot") == default_file

    def test_first_matching_schedule_wins(self, tmp_path):
        file_a = tmp_path / "a.mp3"
        file_b = tmp_path / "b.mp3"
        file_a.write_bytes(b"fake")
        file_b.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {
                "schedule": [
                    {"days": "MON,TUE", "file": str(file_a), "source": "a"},
                    {"days": "MON",     "file": str(file_b), "source": "b"},
                ],
            }}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            with patch("utils.intro_config._INTRO_FILE", tmp_path / "nope.mp3"):
                with patch("utils.intro_config.date") as mock_date:
                    mock_date.today.return_value.weekday.return_value = 0  # Monday
                    from utils.intro_config import get_intro_file
                    assert get_intro_file(99, "bot") == file_a

    def test_schedule_file_missing_falls_back_to_default(self, tmp_path):
        default_file = tmp_path / "default.mp3"
        default_file.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {
                "default":  {"file": str(default_file), "source": "def"},
                "schedule": [{"days": "SAT,SUN", "file": str(tmp_path / "gone.mp3"), "source": "x"}],
            }}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            with patch("utils.intro_config._INTRO_FILE", tmp_path / "nope.mp3"):
                with patch("utils.intro_config.date") as mock_date:
                    mock_date.today.return_value.weekday.return_value = 5  # Saturday
                    from utils.intro_config import get_intro_file
                    assert get_intro_file(99, "bot") == default_file

    def test_no_match_no_default_falls_back_to_env(self, tmp_path):
        fallback = tmp_path / "intro.mp3"
        fallback.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {
                "schedule": [{"days": "SAT,SUN", "file": str(tmp_path / "gone.mp3"), "source": "x"}],
            }}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            with patch("utils.intro_config._INTRO_FILE", fallback):
                with patch("utils.intro_config.date") as mock_date:
                    mock_date.today.return_value.weekday.return_value = 0  # Monday
                    from utils.intro_config import get_intro_file
                    assert get_intro_file(99, "bot") == fallback


# ---------------------------------------------------------------------------
# get_intro_file (existing behaviour preserved)
# ---------------------------------------------------------------------------

class TestGetIntroFile:
    def test_returns_configured_file(self, tmp_path):
        intro = tmp_path / "guild_bot.mp3"
        intro.write_bytes(b"fake")
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps(
            {"99": {"bot": {"file": str(intro), "source": "test.mp3"}}}
        ))
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg_file):
            with patch("utils.intro_config._INTRO_FILE", tmp_path / "nope.mp3"):
                from utils.intro_config import get_intro_file
                assert get_intro_file(99, "bot") == intro

    def test_falls_back_to_env_default(self, tmp_path):
        fallback = tmp_path / "intro.mp3"
        fallback.write_bytes(b"fake")
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text("{}")
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg_file):
            with patch("utils.intro_config._INTRO_FILE", fallback):
                from utils.intro_config import get_intro_file
                assert get_intro_file(99, "bot") == fallback

    def test_returns_none_when_nothing_configured(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text("{}")
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg_file):
            with patch("utils.intro_config._INTRO_FILE", tmp_path / "nope.mp3"):
                from utils.intro_config import get_intro_file
                assert get_intro_file(99, "bot") is None

    def test_ignores_configured_file_if_missing(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps(
            {"99": {"bot": {"file": str(tmp_path / "gone.mp3"), "source": "x"}}}
        ))
        fallback = tmp_path / "fallback.mp3"
        fallback.write_bytes(b"fake")
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg_file):
            with patch("utils.intro_config._INTRO_FILE", fallback):
                from utils.intro_config import get_intro_file
                assert get_intro_file(99, "bot") == fallback

    def test_no_fallback_for_per_member_key(self, tmp_path):
        """Per-member triggers do not fall back to _INTRO_FILE."""
        fallback = tmp_path / "intro.mp3"
        fallback.write_bytes(b"fake")
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text("{}")
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg_file):
            with patch("utils.intro_config._INTRO_FILE", fallback):
                from utils.intro_config import get_intro_file
                assert get_intro_file(99, "user_123") is None


# ---------------------------------------------------------------------------
# get_user_intro (existing behaviour preserved + schedule)
# ---------------------------------------------------------------------------

class TestGetUserIntro:
    def _write_cfg(self, tmp_path, data):
        f = tmp_path / "config.json"
        f.write_text(json.dumps(data))
        return f

    def test_returns_per_member_intro_first(self, tmp_path):
        per_user = tmp_path / "user_42.mp3"
        per_user.write_bytes(b"fake")
        server = tmp_path / "server.mp3"
        server.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {
                "user_42": {"file": str(per_user), "source": "x"},
                "user":    {"file": str(server),   "source": "y"},
            }
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            with patch("utils.intro_config._INTRO_FILE", tmp_path / "nope.mp3"):
                from utils.intro_config import get_user_intro
                assert get_user_intro(99, 42) == per_user

    def test_falls_back_to_server_wide_user(self, tmp_path):
        server = tmp_path / "server.mp3"
        server.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"user": {"file": str(server), "source": "y"}}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            with patch("utils.intro_config._INTRO_FILE", tmp_path / "nope.mp3"):
                from utils.intro_config import get_user_intro
                assert get_user_intro(99, 42) == server

    def test_falls_back_to_env_default(self, tmp_path):
        fallback = tmp_path / "intro.mp3"
        fallback.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {})
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            with patch("utils.intro_config._INTRO_FILE", fallback):
                from utils.intro_config import get_user_intro
                assert get_user_intro(99, 42) == fallback

    def test_returns_none_when_nothing(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {})
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            with patch("utils.intro_config._INTRO_FILE", tmp_path / "nope.mp3"):
                from utils.intro_config import get_user_intro
                assert get_user_intro(99, 42) is None

    def test_skips_missing_per_user_file_and_falls_back(self, tmp_path):
        server = tmp_path / "server.mp3"
        server.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {
                "user_42": {"file": str(tmp_path / "gone.mp3"), "source": "x"},
                "user":    {"file": str(server), "source": "y"},
            }
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            with patch("utils.intro_config._INTRO_FILE", tmp_path / "nope.mp3"):
                from utils.intro_config import get_user_intro
                assert get_user_intro(99, 42) == server

    def test_schedule_override_respected_for_user(self, tmp_path):
        default_file = tmp_path / "default.mp3"
        fri_file     = tmp_path / "friday.mp3"
        default_file.write_bytes(b"fake")
        fri_file.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"user_42": {
                "default":  {"file": str(default_file), "source": "def"},
                "schedule": [{"days": "FRI", "file": str(fri_file), "source": "fri"}],
            }}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            with patch("utils.intro_config._INTRO_FILE", tmp_path / "nope.mp3"):
                with patch("utils.intro_config.date") as mock_date:
                    mock_date.today.return_value.weekday.return_value = 4  # Friday
                    from utils.intro_config import get_user_intro
                    assert get_user_intro(99, 42) == fri_file


# ---------------------------------------------------------------------------
# AutoJoin
# ---------------------------------------------------------------------------

class TestAutoJoin:
    def _write_cfg(self, tmp_path, data):
        f = tmp_path / "config.json"
        f.write_text(json.dumps(data))
        return f

    def test_defaults_to_false(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {})
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import get_auto_join
            assert get_auto_join(99) is False

    def test_returns_true_when_set(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {"99": {"_auto_join": True}})
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import get_auto_join
            assert get_auto_join(99) is True

    def test_set_auto_join_persists(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {})
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import set_auto_join, get_auto_join
            set_auto_join(99, True)
            assert get_auto_join(99) is True
            set_auto_join(99, False)
            assert get_auto_join(99) is False

    def test_set_auto_join_preserves_other_keys(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {"file": "/some.mp3", "source": "x"}}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import set_auto_join, load_intro_config
            set_auto_join(99, True)
            data = load_intro_config()
            assert data["99"]["bot"]["source"] == "x"
            assert data["99"]["_auto_join"] is True


# ---------------------------------------------------------------------------
# set_default_entry
# ---------------------------------------------------------------------------

class TestSetDefaultEntry:
    def _write_cfg(self, tmp_path, data):
        f = tmp_path / "config.json"
        f.write_text(json.dumps(data))
        return f

    def test_creates_new_structured_entry(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {})
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import set_default_entry, load_intro_config
            set_default_entry(99, "bot", "/a.mp3", "song")
            data = load_intro_config()
            assert data["99"]["bot"]["default"] == {"file": "/a.mp3", "source": "song"}

    def test_migrates_flat_format_and_preserves_schedule(self, tmp_path):
        old_file  = tmp_path / "old.mp3"
        sched_file = tmp_path / "sched.mp3"
        old_file.write_bytes(b"fake")
        sched_file.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {
                "default":  {"file": str(old_file), "source": "old"},
                "schedule": [{"days": "SAT,SUN", "file": str(sched_file), "source": "wknd"}],
            }}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import set_default_entry, load_intro_config
            set_default_entry(99, "bot", "/new.mp3", "new_source")
            data = load_intro_config()
            entry = data["99"]["bot"]
            assert entry["default"]["file"] == "/new.mp3"
            assert entry["default"]["source"] == "new_source"
            assert len(entry["schedule"]) == 1  # schedule preserved

    def test_migrates_flat_entry(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {"file": "/old.mp3", "source": "old"}}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import set_default_entry, load_intro_config
            set_default_entry(99, "bot", "/new.mp3", "new")
            data = load_intro_config()
            assert "default" in data["99"]["bot"]
            assert "file" not in data["99"]["bot"]

    def test_saves_member_name(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {})
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import set_default_entry, load_intro_config
            set_default_entry(99, "user_42", "/a.mp3", "song", member_name="Alice#0001")
            data = load_intro_config()
            assert data["99"]["user_42"]["member_name"] == "Alice#0001"


# ---------------------------------------------------------------------------
# set_schedule_entry
# ---------------------------------------------------------------------------

class TestSetScheduleEntry:
    def _write_cfg(self, tmp_path, data):
        f = tmp_path / "config.json"
        f.write_text(json.dumps(data))
        return f

    def test_adds_new_schedule_entry(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {})
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import set_schedule_entry, load_intro_config
            canon = set_schedule_entry(99, "bot", "SAT,SUN", "/wknd.mp3", "weekend")
            assert canon == "SAT,SUN"
            data = load_intro_config()
            sched = data["99"]["bot"]["schedule"]
            assert len(sched) == 1
            assert sched[0] == {"days": "SAT,SUN", "file": "/wknd.mp3", "source": "weekend"}

    def test_replaces_existing_entry_with_same_days(self, tmp_path):
        sched_file = tmp_path / "old_wknd.mp3"
        sched_file.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {
                "schedule": [{"days": "SAT,SUN", "file": str(sched_file), "source": "old"}]
            }}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import set_schedule_entry, load_intro_config
            set_schedule_entry(99, "bot", "WEEKEND", "/new_wknd.mp3", "new")
            data = load_intro_config()
            sched = data["99"]["bot"]["schedule"]
            assert len(sched) == 1
            assert sched[0]["file"] == "/new_wknd.mp3"
            assert not sched_file.exists()  # old file deleted

    def test_normalizes_alias_to_canonical(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {})
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import set_schedule_entry, load_intro_config
            set_schedule_entry(99, "bot", "WEEKDAY", "/wday.mp3", "src")
            data = load_intro_config()
            sched = data["99"]["bot"]["schedule"]
            assert sched[0]["days"] == "MON,TUE,WED,THU,FRI"

    def test_migrates_flat_format(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {"file": "/old.mp3", "source": "old"}}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import set_schedule_entry, load_intro_config
            set_schedule_entry(99, "bot", "SAT,SUN", "/wknd.mp3", "wknd")
            data = load_intro_config()
            entry = data["99"]["bot"]
            assert "file" not in entry
            assert entry["default"]["file"] == "/old.mp3"
            assert len(entry["schedule"]) == 1

    def test_invalid_days_raises(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {})
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import set_schedule_entry
            with pytest.raises(ValueError):
                set_schedule_entry(99, "bot", "INVALID", "/a.mp3", "src")


# ---------------------------------------------------------------------------
# remove_schedule_entry
# ---------------------------------------------------------------------------

class TestRemoveScheduleEntry:
    def _write_cfg(self, tmp_path, data):
        f = tmp_path / "config.json"
        f.write_text(json.dumps(data))
        return f

    def test_removes_existing_entry(self, tmp_path):
        sched_file = tmp_path / "wknd.mp3"
        sched_file.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {
                "schedule": [{"days": "SAT,SUN", "file": str(sched_file), "source": "x"}]
            }}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import remove_schedule_entry, load_intro_config
            result = remove_schedule_entry(99, "bot", "SAT,SUN")
            assert result is True
            assert not sched_file.exists()
            data = load_intro_config()
            assert data["99"]["bot"]["schedule"] == []

    def test_returns_false_when_not_found(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {"schedule": [{"days": "FRI", "file": "/f.mp3", "source": "x"}]}}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import remove_schedule_entry
            result = remove_schedule_entry(99, "bot", "SAT,SUN")
            assert result is False

    def test_matches_via_canonical_form(self, tmp_path):
        sched_file = tmp_path / "wknd.mp3"
        sched_file.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {
                "schedule": [{"days": "SAT,SUN", "file": str(sched_file), "source": "x"}]
            }}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import remove_schedule_entry
            result = remove_schedule_entry(99, "bot", "WEEKEND")
            assert result is True

    def test_leaves_other_schedule_entries_intact(self, tmp_path):
        fri_file = tmp_path / "fri.mp3"
        sat_file = tmp_path / "sat.mp3"
        fri_file.write_bytes(b"fake")
        sat_file.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {
                "schedule": [
                    {"days": "FRI",     "file": str(fri_file), "source": "f"},
                    {"days": "SAT,SUN", "file": str(sat_file), "source": "s"},
                ]
            }}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import remove_schedule_entry, load_intro_config
            remove_schedule_entry(99, "bot", "SAT,SUN")
            data = load_intro_config()
            sched = data["99"]["bot"]["schedule"]
            assert len(sched) == 1
            assert sched[0]["days"] == "FRI"


# ---------------------------------------------------------------------------
# clear_trigger
# ---------------------------------------------------------------------------

class TestClearTrigger:
    def _write_cfg(self, tmp_path, data):
        f = tmp_path / "config.json"
        f.write_text(json.dumps(data))
        return f

    def test_returns_none_when_not_configured(self, tmp_path):
        cfg = self._write_cfg(tmp_path, {})
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import clear_trigger
            assert clear_trigger(99, "bot") is None

    def test_removes_flat_entry_and_deletes_file(self, tmp_path):
        intro = tmp_path / "bot.mp3"
        intro.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {"file": str(intro), "source": "x"}}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import clear_trigger, load_intro_config
            entry = clear_trigger(99, "bot")
            assert entry is not None
            assert not intro.exists()
            data = load_intro_config()
            assert "bot" not in data.get("99", {})

    def test_removes_structured_entry_and_deletes_all_files(self, tmp_path):
        default_file = tmp_path / "default.mp3"
        sched_file   = tmp_path / "wknd.mp3"
        default_file.write_bytes(b"fake")
        sched_file.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {"bot": {
                "default":  {"file": str(default_file), "source": "def"},
                "schedule": [{"days": "SAT,SUN", "file": str(sched_file), "source": "wknd"}],
            }}
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import clear_trigger
            clear_trigger(99, "bot")
            assert not default_file.exists()
            assert not sched_file.exists()

    def test_preserves_other_triggers(self, tmp_path):
        intro = tmp_path / "bot.mp3"
        intro.write_bytes(b"fake")
        cfg = self._write_cfg(tmp_path, {
            "99": {
                "bot":  {"file": str(intro), "source": "x"},
                "user": {"file": "/user.mp3", "source": "y"},
            }
        })
        with patch("utils.intro_config.INTRO_CONFIG_FILE", cfg):
            from utils.intro_config import clear_trigger, load_intro_config
            clear_trigger(99, "bot")
            data = load_intro_config()
            assert "user" in data["99"]
            assert "bot" not in data["99"]
