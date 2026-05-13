"""Unit tests for utils/reaction_config.py."""
import json
from unittest.mock import patch

import pytest


class TestLoadSave:
    def test_load_returns_empty_when_no_file(self, tmp_path):
        with patch("utils.reaction_config.REACTION_CONFIG_FILE", tmp_path / "missing.json"):
            from utils.reaction_config import load_reaction_config
            assert load_reaction_config() == {}

    def test_roundtrip(self, tmp_path):
        cfg = tmp_path / "rc.json"
        data = {"1": {"123:👍": {"channel_id": 456}}}
        with patch("utils.reaction_config.REACTION_CONFIG_FILE", cfg):
            from utils.reaction_config import load_reaction_config, save_reaction_config
            save_reaction_config(data)
            assert load_reaction_config() == data


class TestGetWatches:
    def test_returns_empty_for_unknown_guild(self, tmp_path):
        cfg = tmp_path / "rc.json"
        cfg.write_text("{}")
        with patch("utils.reaction_config.REACTION_CONFIG_FILE", cfg):
            from utils.reaction_config import get_watches
            assert get_watches(99) == {}

    def test_returns_guild_watches(self, tmp_path):
        cfg = tmp_path / "rc.json"
        cfg.write_text(json.dumps({"99": {"123:👍": {"channel_id": 1}}}))
        with patch("utils.reaction_config.REACTION_CONFIG_FILE", cfg):
            from utils.reaction_config import get_watches
            assert "123:👍" in get_watches(99)


class TestAddWatch:
    def test_adds_watch_without_response(self, tmp_path):
        cfg = tmp_path / "rc.json"
        cfg.write_text("{}")
        with patch("utils.reaction_config.REACTION_CONFIG_FILE", cfg):
            from utils.reaction_config import add_watch, get_watches
            add_watch(99, 123, "👍", 456)
            watches = get_watches(99)
            assert "123:👍" in watches
            assert watches["123:👍"]["channel_id"] == 456
            assert "response" not in watches["123:👍"]

    def test_adds_watch_with_response(self, tmp_path):
        cfg = tmp_path / "rc.json"
        cfg.write_text("{}")
        with patch("utils.reaction_config.REACTION_CONFIG_FILE", cfg):
            from utils.reaction_config import add_watch, get_watches
            add_watch(99, 123, "👍", 456, response="Nice one {user}!")
            assert get_watches(99)["123:👍"]["response"] == "Nice one {user}!"

    def test_overwrites_existing_watch(self, tmp_path):
        cfg = tmp_path / "rc.json"
        cfg.write_text("{}")
        with patch("utils.reaction_config.REACTION_CONFIG_FILE", cfg):
            from utils.reaction_config import add_watch, get_watches
            add_watch(99, 123, "👍", 1)
            add_watch(99, 123, "👍", 2, response="updated")
            assert get_watches(99)["123:👍"]["channel_id"] == 2


class TestRemoveWatch:
    def test_removes_existing_watch(self, tmp_path):
        cfg = tmp_path / "rc.json"
        cfg.write_text(json.dumps({"99": {"123:👍": {"channel_id": 1}}}))
        with patch("utils.reaction_config.REACTION_CONFIG_FILE", cfg):
            from utils.reaction_config import remove_watch, get_watches
            assert remove_watch(99, 123, "👍") is True
            assert "123:👍" not in get_watches(99)

    def test_returns_false_when_not_found(self, tmp_path):
        cfg = tmp_path / "rc.json"
        cfg.write_text("{}")
        with patch("utils.reaction_config.REACTION_CONFIG_FILE", cfg):
            from utils.reaction_config import remove_watch
            assert remove_watch(99, 123, "👍") is False
