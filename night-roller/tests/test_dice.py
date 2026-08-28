import random

import pytest

from utils.config import MAX_DICE, MAX_GROUPS, MAX_SIDES
from utils.dice import DiceError, parse, roll


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------

def test_parse_bare_die():
    groups, modifier = parse('d20')
    assert len(groups) == 1
    assert (groups[0].count, groups[0].sides) == (1, 20)
    assert modifier == 0


def test_parse_count_and_modifier():
    groups, modifier = parse('2d6+3')
    assert (groups[0].count, groups[0].sides) == (2, 6)
    assert modifier == 3


def test_parse_negative_modifier():
    _, modifier = parse('d20-2')
    assert modifier == -2


def test_parse_multiple_groups():
    groups, modifier = parse('d20+2d4+1')
    assert [(g.count, g.sides) for g in groups] == [(1, 20), (2, 4)]
    assert modifier == 1


def test_parse_subtracted_group():
    groups, _ = parse('2d6-1d4')
    assert groups[1].negative is True


def test_parse_is_whitespace_and_case_insensitive():
    groups, modifier = parse(' 2D6 + 3 ')
    assert (groups[0].count, groups[0].sides, modifier) == (2, 6, 3)


@pytest.mark.parametrize('expr', ['', '   ', 'banana', 'd', '2d', 'd20+', '2d6++3', '1d6d4'])
def test_parse_rejects_garbage(expr):
    with pytest.raises(DiceError):
        parse(expr)


def test_parse_rejects_too_many_dice():
    with pytest.raises(DiceError, match='Too many dice'):
        parse(f'{MAX_DICE + 1}d6')


def test_parse_rejects_too_many_sides():
    with pytest.raises(DiceError, match='too big'):
        parse(f'd{MAX_SIDES + 1}')


def test_parse_rejects_one_sided_die():
    with pytest.raises(DiceError, match='at least 2 sides'):
        parse('d1')


def test_parse_rejects_too_many_groups():
    with pytest.raises(DiceError, match='Too many dice groups'):
        parse('+'.join(['d6'] * (MAX_GROUPS + 1)))


# ---------------------------------------------------------------------------
# roll
# ---------------------------------------------------------------------------

def test_roll_within_bounds():
    for _ in range(200):
        result = roll('d20')
        assert 1 <= result.total <= 20


def test_roll_applies_modifier():
    for _ in range(50):
        result = roll('2d6+3')
        assert 5 <= result.total <= 15
        assert result.modifier == 3


def test_roll_subtracts_negative_group():
    for _ in range(50):
        result = roll('2d6-1d4')
        assert -2 <= result.total <= 11


def test_roll_total_matches_parts():
    result = roll('3d8+2d4-1')
    expected = sum(g.subtotal for g in result.groups) + result.modifier
    assert result.total == expected


def test_roll_is_deterministic_with_seeded_rng():
    first = roll('4d6+2', rng=random.Random(99))
    second = roll('4d6+2', rng=random.Random(99))
    assert first.total == second.total
    assert [g.rolls for g in first.groups] == [g.rolls for g in second.groups]


def test_roll_keep_high_keeps_one_die():
    result = roll('2d20', keep='high', rng=random.Random(7))
    group = result.groups[0]
    assert len(group.rolls) == 1
    assert len(group.dropped) == 1
    assert group.rolls[0] >= group.dropped[0]


def test_roll_keep_low_keeps_the_worst():
    result = roll('2d20', keep='low', rng=random.Random(7))
    group = result.groups[0]
    assert group.rolls[0] <= group.dropped[0]


def test_roll_keep_only_affects_first_group():
    result = roll('2d20+2d6', keep='high', rng=random.Random(3))
    assert len(result.groups[0].rolls) == 1
    assert len(result.groups[1].rolls) == 2


def test_roll_rejects_unknown_keep_mode():
    with pytest.raises(DiceError):
        roll('d20', keep='sideways')


# ---------------------------------------------------------------------------
# RollResult helpers
# ---------------------------------------------------------------------------

def test_natural_returns_face_for_single_die():
    result = roll('d20', rng=random.Random(5))
    assert result.natural == result.groups[0].rolls[0]


def test_natural_is_none_for_multiple_dice():
    assert roll('2d6').natural is None


def test_is_single_d20_true_with_modifier():
    assert roll('d20+5').is_single_d20 is True


def test_is_single_d20_false_for_other_dice():
    assert roll('d6').is_single_d20 is False


def test_advantage_still_counts_as_single_d20():
    assert roll('2d20', keep='high').is_single_d20 is True


def test_breakdown_shows_rolls_and_modifier():
    result = roll('2d6+3', rng=random.Random(1))
    text = result.breakdown()
    assert text.startswith('[')
    assert text.endswith('+ 3')


def test_breakdown_marks_dropped_dice():
    result = roll('2d20', keep='high', rng=random.Random(2))
    assert '~~' in result.breakdown()


def test_breakdown_of_negative_group():
    result = roll('2d6-1d4', rng=random.Random(4))
    assert '- [' in result.breakdown()
