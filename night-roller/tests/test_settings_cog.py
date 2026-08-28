import pytest

from cogs.settings import SettingsCog
from conftest import sent_embed
from utils.guild_config import (
    get_die,
    get_difficulty,
    get_subtract_ones,
    get_system,
    is_wod,
)


def _cog(mock_bot) -> SettingsCog:
    return SettingsCog(mock_bot)


# ---------------------------------------------------------------------------
# !config show
# ---------------------------------------------------------------------------

async def test_config_shows_current_settings(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.config.callback(cog, ctx)
    embed = sent_embed(ctx)
    assert 'standard' in embed.description
    assert 'd20' in embed.description


async def test_config_show_subcommand(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.config_show.callback(cog, ctx)
    ctx.send.assert_awaited_once()


# ---------------------------------------------------------------------------
# !config system
# ---------------------------------------------------------------------------

async def test_switch_to_wod(mock_bot, ctx, guild_id):
    cog = _cog(mock_bot)
    await cog.config_system.callback(cog, ctx, system='wod')
    assert is_wod(guild_id) is True
    assert get_die(guild_id) == 10


async def test_switch_back_to_standard(mock_bot, ctx, guild_id):
    cog = _cog(mock_bot)
    await cog.config_system.callback(cog, ctx, system='wod')
    await cog.config_system.callback(cog, ctx, system='standard')
    assert get_system(guild_id) == 'standard'


async def test_wod_confirmation_mentions_difficulty(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.config_system.callback(cog, ctx, system='wod')
    assert 'Difficulty' in sent_embed(ctx).description


async def test_unknown_system_is_reported(mock_bot, ctx, guild_id):
    cog = _cog(mock_bot)
    await cog.config_system.callback(cog, ctx, system='shadowrun')
    assert 'Setting not changed' in sent_embed(ctx).title
    assert get_system(guild_id) == 'standard'


# ---------------------------------------------------------------------------
# !config die / difficulty / ones
# ---------------------------------------------------------------------------

async def test_set_die(mock_bot, ctx, guild_id):
    cog = _cog(mock_bot)
    await cog.config_die.callback(cog, ctx, sides=12)
    assert get_die(guild_id) == 12


async def test_set_die_rejects_nonsense(mock_bot, ctx, guild_id):
    cog = _cog(mock_bot)
    await cog.config_die.callback(cog, ctx, sides=1)
    assert 'Setting not changed' in sent_embed(ctx).title
    assert get_die(guild_id) == 20


async def test_set_difficulty(mock_bot, ctx, guild_id):
    cog = _cog(mock_bot)
    await cog.config_system.callback(cog, ctx, system='wod')
    await cog.config_difficulty.callback(cog, ctx, difficulty=8)
    assert get_difficulty(guild_id) == 8


async def test_impossible_difficulty_is_reported(mock_bot, ctx, guild_id):
    cog = _cog(mock_bot)
    await cog.config_system.callback(cog, ctx, system='wod')  # d10
    await cog.config_difficulty.callback(cog, ctx, difficulty=11)
    assert 'Setting not changed' in sent_embed(ctx).title
    assert get_difficulty(guild_id) == 6


@pytest.mark.parametrize('word', ['off', 'false', 'no', '0'])
async def test_ones_off(mock_bot, ctx, guild_id, word):
    cog = _cog(mock_bot)
    await cog.config_ones.callback(cog, ctx, state=word)
    assert get_subtract_ones(guild_id) is False


@pytest.mark.parametrize('word', ['on', 'true', 'yes', '1'])
async def test_ones_on(mock_bot, ctx, guild_id, word):
    cog = _cog(mock_bot)
    await cog.config_ones.callback(cog, ctx, state='off')
    await cog.config_ones.callback(cog, ctx, state=word)
    assert get_subtract_ones(guild_id) is True


async def test_ones_rejects_gibberish(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.config_ones.callback(cog, ctx, state='maybe')
    assert 'Setting not changed' in sent_embed(ctx).title


# ---------------------------------------------------------------------------
# !config reset
# ---------------------------------------------------------------------------

async def test_reset_clears_overrides(mock_bot, ctx, guild_id):
    cog = _cog(mock_bot)
    await cog.config_system.callback(cog, ctx, system='wod')
    await cog.config_reset.callback(cog, ctx)
    assert get_system(guild_id) == 'standard'
    assert get_die(guild_id) == 20
