"""Success counting: the World of Darkness style pool roll."""

import random

import pytest

from utils.dice import DiceError, roll


class _Faces(random.Random):
    """An RNG that deals a fixed sequence of die faces."""

    def __init__(self, faces):
        super().__init__()
        self._faces = list(faces)

    def randint(self, a, b):
        return self._faces.pop(0)


def rolled(faces, expression=None, **kwargs):
    expression = expression or f'{len(faces)}d10'
    return roll(expression, rng=_Faces(faces), **kwargs)


# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------

def test_counts_dice_at_or_above_target():
    result = rolled([6, 5, 7, 2, 10], target=6)
    assert result.hits == 3  # 6, 7, 10


def test_target_is_inclusive():
    assert rolled([6], target=6).hits == 1
    assert rolled([5], target=6).hits == 0


def test_no_target_means_sum_mode():
    result = rolled([6, 5], '2d10')
    assert result.counts_successes is False
    assert result.total == 11
    assert result.hits == 0


def test_counts_successes_flag_is_set_with_target():
    assert rolled([6], target=6).counts_successes is True


def test_faces_collects_every_die():
    assert rolled([1, 2, 3], target=6).faces == [1, 2, 3]


# ---------------------------------------------------------------------------
# The botch rule
# ---------------------------------------------------------------------------

def test_ones_are_ignored_when_the_rule_is_off():
    result = rolled([1, 1, 8], target=6, subtract_ones=False)
    assert result.ones == 0
    assert result.net_hits == 1


def test_ones_cancel_successes():
    result = rolled([1, 8, 9], target=6, subtract_ones=True)
    assert result.hits == 2
    assert result.ones == 1
    assert result.net_hits == 1


def test_net_can_go_negative():
    result = rolled([1, 1, 5], target=6, subtract_ones=True)
    assert result.net_hits == -2


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------

def test_outcome_success():
    assert rolled([8, 9], target=6, subtract_ones=True).outcome == 'success'


def test_outcome_failure_when_nothing_hits():
    assert rolled([2, 3], target=6, subtract_ones=True).outcome == 'failure'


def test_outcome_failure_when_ones_cancel_everything():
    """One hit, one 1 — a wash, not a botch."""
    result = rolled([1, 8], target=6, subtract_ones=True)
    assert result.net_hits == 0
    assert result.outcome == 'failure'


def test_outcome_botch_when_ones_outnumber_hits():
    assert rolled([1, 1, 8], target=6, subtract_ones=True).outcome == 'botch'


def test_outcome_botch_with_no_hits_at_all():
    assert rolled([1, 4, 5], target=6, subtract_ones=True).outcome == 'botch'


def test_no_botch_without_the_rule():
    assert rolled([1, 1, 5], target=6, subtract_ones=False).outcome == 'failure'


# ---------------------------------------------------------------------------
# Interaction with the rest of the engine
# ---------------------------------------------------------------------------

def test_target_rejects_zero():
    with pytest.raises(DiceError, match='at least 1'):
        roll('5d10', target=0)


def test_successes_work_across_multiple_groups():
    result = rolled([8, 2, 9, 1], '2d10+2d6', target=6, subtract_ones=True)
    assert result.hits == 2
    assert result.ones == 1
    assert result.net_hits == 1


def test_dropped_dice_do_not_count_as_hits():
    """Advantage keeps one die — the discarded one must not score."""
    result = roll('2d10', keep='high', target=6, subtract_ones=True, rng=_Faces([9, 8]))
    assert result.faces == [9]
    assert result.hits == 1


def test_breakdown_marks_hits_in_bold():
    result = rolled([8, 2], target=6)
    assert '**8**' in result.breakdown()
    assert '**2**' not in result.breakdown()


def test_breakdown_marks_cancelling_ones():
    result = rolled([1, 8], target=6, subtract_ones=True)
    assert '__1__' in result.breakdown()


def test_breakdown_leaves_ones_plain_when_rule_is_off():
    result = rolled([1, 8], target=6, subtract_ones=False)
    assert '__1__' not in result.breakdown()


def test_sum_mode_breakdown_has_no_markup():
    text = rolled([6, 5], '2d10').breakdown()
    assert '**' not in text and '__' not in text
