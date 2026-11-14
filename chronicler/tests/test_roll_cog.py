import pytest

from cogs.roll import (
    RollCog,
    advantage_expression,
    is_bare_pool,
    resolve_expression,
    split_input,
)
from conftest import sent_embed


# ---------------------------------------------------------------------------
# split_input
# ---------------------------------------------------------------------------

def test_split_empty():
    assert split_input('') == (None, '', None, '')


def test_split_expression_only():
    assert split_input('2d6+3') == (None, '2d6+3', None, '')


def test_split_expression_and_reason():
    assert split_input('2d6+3 sneak attack') == (None, '2d6+3', None, 'sneak attack')


def test_split_joins_spaced_expression():
    assert split_input('2d6 + 3') == (None, '2d6+3', None, '')


@pytest.mark.parametrize('word', ['adv', 'advantage', 'a'])
def test_split_detects_advantage(word):
    keep, expr, _, _ = split_input(f'{word} +5')
    assert keep == 'high'
    assert expr == '+5'


@pytest.mark.parametrize('word', ['dis', 'disadvantage', 'disadv'])
def test_split_detects_disadvantage(word):
    keep, _, _, _ = split_input(f'{word} +5')
    assert keep == 'low'


def test_split_advantage_with_reason():
    assert split_input('adv +5 to hit') == ('high', '+5', None, 'to hit')


def test_split_reason_only():
    assert split_input('for the horde') == (None, '', None, 'for the horde')


# ---------------------------------------------------------------------------
# advantage_expression
# ---------------------------------------------------------------------------

def test_advantage_expression_defaults_to_two_d20():
    assert advantage_expression('') == '2d20'


def test_advantage_expression_from_bare_modifier():
    assert advantage_expression('+5') == '2d20+5'
    assert advantage_expression('5') == '2d20+5'
    assert advantage_expression('-2') == '2d20-2'


def test_advantage_expression_doubles_first_group():
    assert advantage_expression('d20+5') == '2d20+5'
    assert advantage_expression('2d20+5') == '4d20+5'


def test_advantage_expression_leaves_later_groups_alone():
    assert advantage_expression('d20+2d6') == '2d20+2d6'


# ---------------------------------------------------------------------------
# !roll
# ---------------------------------------------------------------------------

def _cog(mock_bot) -> RollCog:
    return RollCog(mock_bot)


async def test_roll_bare_uses_default_die(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='')
    embed = sent_embed(ctx)
    assert '1d20' in embed.title


async def test_roll_with_expression(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='2d6+3')
    embed = sent_embed(ctx)
    assert '2d6' in embed.title


async def test_roll_shows_roller_name(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='d20')
    assert 'TestUser' in sent_embed(ctx).title


async def test_roll_advantage(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='adv +5')
    embed = sent_embed(ctx)
    assert 'advantage' in embed.title
    assert '2d20' in embed.title


async def test_roll_disadvantage(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='dis')
    assert 'disadvantage' in sent_embed(ctx).title


async def test_roll_includes_reason(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='2d6+3 sneak attack')
    assert 'sneak attack' in sent_embed(ctx).description


async def test_roll_reason_only_still_rolls_default(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='for the horde')
    embed = sent_embed(ctx)
    assert '1d20' in embed.title
    assert 'for the horde' in embed.description


async def test_roll_invalid_expression_sends_error(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='9999d6')
    embed = sent_embed(ctx)
    assert 'Bad roll' in embed.title


async def test_roll_sends_exactly_one_message(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='d20')
    ctx.send.assert_awaited_once()


# ---------------------------------------------------------------------------
# Difficulty in parentheses
# ---------------------------------------------------------------------------

def test_split_reads_target_in_parens():
    assert split_input('5 (6)') == (None, '5', 6, '')


def test_split_reads_target_without_space():
    assert split_input('5(6)') == (None, '5', 6, '')


def test_split_target_with_dice_and_reason():
    assert split_input('6d10 (7) intimidate') == (None, '6d10', 7, 'intimidate')


def test_split_target_before_expression():
    assert split_input('(7) 6d10') == (None, '6d10', 7, '')


def test_split_no_target_stays_none():
    assert split_input('2d6+3')[2] is None


# ---------------------------------------------------------------------------
# Bare pools
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('text,expected', [('5', True), ('12', True), ('2d6', False),
                                           ('', False), ('+5', False), ('d20', False)])
def test_is_bare_pool(text, expected):
    assert is_bare_pool(text) is expected


def test_resolve_expression_expands_a_pool():
    assert resolve_expression('5', 10) == '5d10'


def test_resolve_expression_defaults_to_one_die():
    assert resolve_expression('', 10) == '1d10'


def test_resolve_expression_passes_notation_through():
    assert resolve_expression('2d6+3d8', 10) == '2d6+3d8'


# ---------------------------------------------------------------------------
# Standard server behaviour
# ---------------------------------------------------------------------------

async def test_bare_pool_uses_the_server_die(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='5')
    assert '5d20' in sent_embed(ctx).title


async def test_standard_server_sums_by_default(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='5')
    assert 'difficulty' not in sent_embed(ctx).title


async def test_target_counts_hits_in_a_standard_server(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='6d10 (7)')
    embed = sent_embed(ctx)
    assert 'difficulty 7' in embed.title
    assert 'at 7+' in embed.description


async def test_expression_still_works_unchanged(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='2d6+3d8')
    embed = sent_embed(ctx)
    assert '2d6 + 3d8' in embed.title
    assert 'difficulty' not in embed.title


async def test_oversized_pool_is_refused(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='9999')
    assert 'Pool too big' in sent_embed(ctx).title


# ---------------------------------------------------------------------------
# World of Darkness server behaviour
# ---------------------------------------------------------------------------

async def test_wod_pool_rolls_d10s(mock_bot, ctx, wod_guild):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='5')
    assert '5d10' in sent_embed(ctx).title


async def test_wod_pool_uses_default_difficulty(mock_bot, ctx, wod_guild):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='5')
    assert 'difficulty 6' in sent_embed(ctx).title


async def test_wod_explicit_difficulty_wins(mock_bot, ctx, wod_guild):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='5 (5)')
    embed = sent_embed(ctx)
    assert '5d10' in embed.title
    assert 'difficulty 5' in embed.title


async def test_wod_bare_roll_is_one_die(mock_bot, ctx, wod_guild):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='')
    assert '1d10' in sent_embed(ctx).title


async def test_wod_leaves_explicit_expressions_summed(mock_bot, ctx, wod_guild):
    """!roll 2d6+3d8 must keep working the old way even in a WoD server."""
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='2d6+3d8')
    embed = sent_embed(ctx)
    assert 'difficulty' not in embed.title


async def test_wod_roll_reports_hits(mock_bot, ctx, wod_guild):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='5')
    assert 'at 6+' in sent_embed(ctx).description


async def test_wod_roll_accepts_a_label(mock_bot, ctx, wod_guild):
    cog = _cog(mock_bot)
    await cog.roll_cmd.callback(cog, ctx, args='5 (5) intimidate')
    assert 'intimidate' in sent_embed(ctx).description
