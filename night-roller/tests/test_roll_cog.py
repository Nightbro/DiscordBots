import pytest

from cogs.roll import RollCog, advantage_expression, split_input
from conftest import sent_embed


# ---------------------------------------------------------------------------
# split_input
# ---------------------------------------------------------------------------

def test_split_empty():
    assert split_input('') == (None, '', '')


def test_split_expression_only():
    assert split_input('2d6+3') == (None, '2d6+3', '')


def test_split_expression_and_reason():
    assert split_input('2d6+3 sneak attack') == (None, '2d6+3', 'sneak attack')


def test_split_joins_spaced_expression():
    assert split_input('2d6 + 3') == (None, '2d6+3', '')


@pytest.mark.parametrize('word', ['adv', 'advantage', 'a'])
def test_split_detects_advantage(word):
    keep, expr, _ = split_input(f'{word} +5')
    assert keep == 'high'
    assert expr == '+5'


@pytest.mark.parametrize('word', ['dis', 'disadvantage', 'disadv'])
def test_split_detects_disadvantage(word):
    keep, _, _ = split_input(f'{word} +5')
    assert keep == 'low'


def test_split_advantage_with_reason():
    assert split_input('adv +5 to hit') == ('high', '+5', 'to hit')


def test_split_reason_only():
    assert split_input('for the horde') == (None, '', 'for the horde')


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
