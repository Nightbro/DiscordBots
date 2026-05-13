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
