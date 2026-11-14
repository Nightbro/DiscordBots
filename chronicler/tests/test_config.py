import re

from utils import config


def test_bot_identity_loaded():
    assert config.BOT_NAME
    assert config.PREFIX == '!'
    assert isinstance(config.COLOR, int)


def test_dice_limits_are_sane():
    assert config.MAX_DICE >= 1
    assert config.MAX_SIDES >= 20
    assert config.MAX_GROUPS >= 1
    assert isinstance(config.SHOW_ROLLS, bool)


def test_dice_defaults_are_usable():
    assert config.DEFAULT_SYSTEM in ('standard', 'wod')
    assert 2 <= config.DEFAULT_DIE <= config.MAX_SIDES
    assert 1 <= config.DEFAULT_DIFFICULTY <= config.DEFAULT_DIE
    assert isinstance(config.DEFAULT_SUBTRACT_ONES, bool)


def test_version_has_base_and_commit():
    # e.g. "1.0.42 (abc1234)"
    assert re.match(r'^\d+\.\d+\.\d+ \(.+\)$', config.VERSION)


def test_paths_derived_from_base_dir():
    """Every runtime path hangs off BASE_DIR — nothing hardcodes data/.

    GUILD_CONFIG_FILE is not compared against DATA_DIR here: the autouse
    isolated_guild_config fixture redirects it to a temp directory for every
    test, so only its filename is stable.
    """
    assert config.DATA_DIR == config.BASE_DIR / 'data'
    assert config.LOGS_DIR == config.DATA_DIR / 'logs'
    assert config.GUILD_CONFIG_FILE.name == 'guild_config.json'
    assert config.LOGS_DIR.exists()


def test_invite_url_is_a_string():
    """Blank until the Discord application exists, but always present."""
    assert isinstance(config.INVITE_URL, str)
