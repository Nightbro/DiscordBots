import pytest

from utils.config import DEFAULT_DIE, DEFAULT_DIFFICULTY, DEFAULT_SYSTEM, MAX_SIDES
from utils.guild_config import (
    SettingError,
    get_all_settings,
    get_die,
    get_difficulty,
    get_subtract_ones,
    get_system,
    is_wod,
    reset_guild,
    set_die,
    set_difficulty,
    set_subtract_ones,
    set_system,
)
from utils.persistence import GuildConfig

OTHER_GUILD = 999888777


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def test_unconfigured_guild_gets_global_defaults(guild_id):
    assert get_system(guild_id) == DEFAULT_SYSTEM
    assert get_die(guild_id) == DEFAULT_DIE
    assert get_difficulty(guild_id) == DEFAULT_DIFFICULTY


def test_unconfigured_guild_is_not_wod(guild_id):
    assert is_wod(guild_id) is False


def test_get_all_settings_returns_every_key(guild_id):
    settings = get_all_settings(guild_id)
    assert set(settings) == {'system', 'die', 'difficulty', 'subtract_ones'}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_setting_survives_a_reload(guild_id):
    set_die(guild_id, 12)
    assert GuildConfig().get(str(guild_id))['die'] == 12
    assert get_die(guild_id) == 12


def test_guilds_are_independent(guild_id):
    set_system(guild_id, 'wod')
    assert is_wod(guild_id) is True
    assert is_wod(OTHER_GUILD) is False
    assert get_die(OTHER_GUILD) == DEFAULT_DIE


def test_reset_restores_defaults(guild_id):
    set_system(guild_id, 'wod')
    set_difficulty(guild_id, 8)
    reset_guild(guild_id)
    assert get_system(guild_id) == DEFAULT_SYSTEM
    assert get_die(guild_id) == DEFAULT_DIE
    assert get_difficulty(guild_id) == DEFAULT_DIFFICULTY


def test_missing_file_is_not_an_error(guild_id):
    """A fresh install has no guild_config.json at all."""
    assert get_all_settings(guild_id)


def test_corrupt_file_falls_back_to_defaults(guild_id):
    GuildConfig().path.write_text('{ this is not json', encoding='utf-8')
    assert get_system(guild_id) == DEFAULT_SYSTEM


# ---------------------------------------------------------------------------
# set_system
# ---------------------------------------------------------------------------

def test_switching_to_wod_moves_the_die_to_d10(guild_id):
    set_system(guild_id, 'wod')
    assert get_die(guild_id) == 10


def test_switching_system_keeps_an_explicit_die(guild_id):
    set_die(guild_id, 6)
    set_system(guild_id, 'wod')
    assert get_die(guild_id) == 6


def test_system_is_case_insensitive(guild_id):
    assert set_system(guild_id, 'WoD') == 'wod'


def test_unknown_system_is_rejected(guild_id):
    with pytest.raises(SettingError, match='Unknown system'):
        set_system(guild_id, 'shadowrun')


# ---------------------------------------------------------------------------
# set_die / set_difficulty / set_subtract_ones
# ---------------------------------------------------------------------------

def test_die_accepts_any_size(guild_id):
    assert set_die(guild_id, 37) == 37


@pytest.mark.parametrize('sides', [1, 0, -6])
def test_die_rejects_degenerate_sizes(guild_id, sides):
    with pytest.raises(SettingError):
        set_die(guild_id, sides)


def test_die_rejects_oversized(guild_id):
    with pytest.raises(SettingError):
        set_die(guild_id, MAX_SIDES + 1)


def test_difficulty_is_stored(guild_id):
    set_system(guild_id, 'wod')
    assert set_difficulty(guild_id, 8) == 8
    assert get_difficulty(guild_id) == 8


def test_difficulty_above_the_die_is_rejected(guild_id):
    """Difficulty 11 on a d10 can never succeed — catch it at config time."""
    set_system(guild_id, 'wod')  # die becomes 10
    with pytest.raises(SettingError, match='impossible'):
        set_difficulty(guild_id, 11)


def test_difficulty_below_one_is_rejected(guild_id):
    with pytest.raises(SettingError):
        set_difficulty(guild_id, 0)


def test_subtract_ones_toggles(guild_id):
    set_subtract_ones(guild_id, False)
    assert get_subtract_ones(guild_id) is False
    set_subtract_ones(guild_id, True)
    assert get_subtract_ones(guild_id) is True
