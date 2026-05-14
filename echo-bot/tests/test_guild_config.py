import pytest
from unittest.mock import patch, MagicMock

from utils.guild_config import (
    get_setting,
    set_setting,
    reset_setting,
    get_all_settings,
    get_auto_join,
    get_auto_leave,
)
from utils.config import AUTO_JOIN, AUTO_LEAVE


@pytest.fixture()
def mock_cfg():
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

    with patch('utils.guild_config.GuildConfig', return_value=_FakeCfg()):
        yield store


# ---------------------------------------------------------------------------
# get_setting — fallback to global default
# ---------------------------------------------------------------------------

def test_get_setting_returns_global_default_when_no_override(mock_cfg):
    assert get_setting(123, 'auto_join') == AUTO_JOIN
    assert get_setting(123, 'auto_leave') == AUTO_LEAVE


def test_get_setting_returns_override_when_set(mock_cfg):
    set_setting(123, 'auto_join', True)
    assert get_setting(123, 'auto_join') is True


def test_get_setting_different_guilds_independent(mock_cfg):
    set_setting(111, 'auto_join', True)
    set_setting(222, 'auto_join', False)
    assert get_setting(111, 'auto_join') is True
    assert get_setting(222, 'auto_join') is False


# ---------------------------------------------------------------------------
# set_setting / reset_setting
# ---------------------------------------------------------------------------

def test_set_then_reset_reverts_to_default(mock_cfg):
    set_setting(123, 'auto_leave', False)
    assert get_setting(123, 'auto_leave') is False
    reset_setting(123, 'auto_leave')
    assert get_setting(123, 'auto_leave') == AUTO_LEAVE


def test_reset_setting_noop_when_not_set(mock_cfg):
    reset_setting(123, 'auto_join')  # should not raise
    assert get_setting(123, 'auto_join') == AUTO_JOIN


# ---------------------------------------------------------------------------
# get_all_settings
# ---------------------------------------------------------------------------

def test_get_all_settings_includes_all_keys(mock_cfg):
    settings = get_all_settings(123)
    assert 'auto_join' in settings
    assert 'auto_leave' in settings


def test_get_all_settings_reflects_override(mock_cfg):
    set_setting(123, 'auto_join', True)
    settings = get_all_settings(123)
    assert settings['auto_join'] is True
    assert settings['auto_leave'] == AUTO_LEAVE


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def test_get_auto_join_default(mock_cfg):
    assert get_auto_join(123) == AUTO_JOIN


def test_get_auto_leave_default(mock_cfg):
    assert get_auto_leave(123) == AUTO_LEAVE


def test_get_auto_join_override(mock_cfg):
    set_setting(123, 'auto_join', True)
    assert get_auto_join(123) is True


def test_get_auto_leave_override(mock_cfg):
    set_setting(123, 'auto_leave', False)
    assert get_auto_leave(123) is False
