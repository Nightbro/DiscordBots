"""Rendering a roll as text — the presentation the engine deliberately omits."""

import random

from utils import format as fmt
from utils.dice import roll


class _Faces(random.Random):
    """An RNG that deals a fixed sequence of die faces."""

    def __init__(self, faces):
        super().__init__()
        self._faces = list(faces)

    def randint(self, a, b):
        return self._faces.pop(0)


def _pool(faces, target=6, subtract_ones=True):
    return roll(
        f'{len(faces)}d10',
        target=target,
        subtract_ones=subtract_ones,
        rng=_Faces(faces),
    )


# ---------------------------------------------------------------------------
# notation
# ---------------------------------------------------------------------------

def test_notation_is_signed():
    assert fmt.notation(roll('2d6-1d4')) == '2d6 - 1d4'


def test_notation_of_single_group():
    assert fmt.notation(roll('3d8')) == '3d8'


# ---------------------------------------------------------------------------
# breakdown
# ---------------------------------------------------------------------------

def test_breakdown_shows_rolls_and_modifier():
    text = fmt.breakdown(roll('2d6+3', rng=random.Random(1)))
    assert text.startswith('[')
    assert text.endswith('+ 3')


def test_breakdown_marks_dropped_dice():
    result = roll('2d20', keep='high', rng=random.Random(2))
    assert '~~' in fmt.breakdown(result)


def test_breakdown_of_negative_group():
    result = roll('2d6-1d4', rng=random.Random(4))
    assert '- [' in fmt.breakdown(result)


def test_breakdown_marks_hits_in_bold():
    text = fmt.breakdown(_pool([8, 2]))
    assert '**8**' in text
    assert '**2**' not in text


def test_breakdown_marks_cancelling_ones():
    assert '__1__' in fmt.breakdown(_pool([1, 8]))


def test_breakdown_leaves_ones_plain_when_rule_is_off():
    text = fmt.breakdown(_pool([1, 8], subtract_ones=False))
    assert '__1__' not in text


def test_sum_mode_breakdown_has_no_markup():
    text = fmt.breakdown(roll('2d10', rng=_Faces([6, 5])))
    assert '**' not in text and '__' not in text


# ---------------------------------------------------------------------------
# compact_breakdown
# ---------------------------------------------------------------------------

def test_compact_breakdown_uses_subtotals():
    text = fmt.compact_breakdown(roll('2d6+3d8', rng=random.Random(14)))
    assert '2d6(' in text and '3d8(' in text
    assert '[' not in text


def test_compact_breakdown_keeps_modifier_and_signs():
    text = fmt.compact_breakdown(roll('2d6-1d4+5', rng=random.Random(15)))
    assert '- 1d4(' in text
    assert text.endswith('+ 5')


def test_compact_breakdown_is_much_shorter_for_big_rolls():
    result = roll('200d20', rng=random.Random(16))
    assert len(fmt.compact_breakdown(result)) < len(fmt.breakdown(result)) / 10


# ---------------------------------------------------------------------------
# wrap
# ---------------------------------------------------------------------------

def test_wrap_adds_a_code_span_to_plain_text():
    assert fmt.wrap('[4, 6] + 3') == '`[4, 6] + 3`'


def test_wrap_leaves_bold_alone():
    """Discord renders nothing inside a code span, so markup must stay bare."""
    assert fmt.wrap('[**8**, 2]') == '[**8**, 2]'


def test_wrap_leaves_underline_and_strikethrough_alone():
    assert fmt.wrap('[__1__]') == '[__1__]'
    assert fmt.wrap('[5, ~~2~~]') == '[5, ~~2~~]'
