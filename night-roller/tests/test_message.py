import random

from utils.config import BOT_NAME
from utils.dice import roll
from utils.message import MessageWriter


def test_success_error_info_have_titles():
    assert 'Nice' in MessageWriter.success('Nice').title
    assert 'Oops' in MessageWriter.error('Oops').title
    assert 'FYI' in MessageWriter.info('FYI').title


def test_footer_is_bot_name():
    assert MessageWriter.info('x').footer.text == BOT_NAME


def test_roll_card_shows_total_and_roller():
    result = roll('2d6+3', rng=random.Random(1))
    embed = MessageWriter.roll_card(result, 'TestUser')
    assert 'TestUser' in embed.title
    assert '2d6' in embed.title
    assert str(result.total) in embed.description


def test_roll_card_shows_breakdown():
    result = roll('2d6+3', rng=random.Random(1))
    embed = MessageWriter.roll_card(result, 'TestUser')
    assert result.breakdown() in embed.description


def test_roll_card_labels_advantage():
    result = roll('2d20', keep='high', rng=random.Random(1))
    embed = MessageWriter.roll_card(result, 'TestUser')
    assert 'advantage' in embed.title


def test_roll_card_labels_disadvantage():
    result = roll('2d20', keep='low', rng=random.Random(1))
    embed = MessageWriter.roll_card(result, 'TestUser')
    assert 'disadvantage' in embed.title


def test_roll_card_includes_reason():
    result = roll('d20', rng=random.Random(1))
    embed = MessageWriter.roll_card(result, 'TestUser', reason='to hit')
    assert 'to hit' in embed.description


def _forced_d20(face: int):
    class _Fixed(random.Random):
        def randint(self, a, b):
            return face

    return roll('d20', rng=_Fixed())


def test_roll_card_celebrates_natural_20():
    embed = MessageWriter.roll_card(_forced_d20(20), 'TestUser')
    assert 'Natural 20' in embed.description


def test_roll_card_mourns_natural_1():
    embed = MessageWriter.roll_card(_forced_d20(1), 'TestUser')
    assert 'Natural 1' in embed.description


def test_roll_card_no_flavour_for_mid_roll():
    embed = MessageWriter.roll_card(_forced_d20(12), 'TestUser')
    assert 'Natural' not in embed.description


def test_roll_card_title_uses_signed_notation():
    result = roll('2d6-1d4', rng=random.Random(2))
    embed = MessageWriter.roll_card(result, 'TestUser')
    assert '2d6 - 1d4' in embed.title


def test_roll_card_handles_nonstandard_dice():
    result = roll('3d37', rng=random.Random(3))
    embed = MessageWriter.roll_card(result, 'TestUser')
    assert '3d37' in embed.title


def test_roll_card_stays_within_discord_limits_for_huge_rolls():
    result = roll('500d20+500d20', rng=random.Random(4))
    embed = MessageWriter.roll_card(result, 'TestUser', reason='chaos')
    assert len(embed.title) <= 256
    assert len(embed.description) <= 4096


def test_roll_card_falls_back_to_compact_breakdown_when_too_long():
    result = roll('300d20', rng=random.Random(5))
    embed = MessageWriter.roll_card(result, 'TestUser')
    assert '300d20(' in embed.description  # subtotal form, not every face


def test_roll_card_still_shows_total_for_huge_rolls():
    result = roll('300d20', rng=random.Random(6))
    embed = MessageWriter.roll_card(result, 'TestUser')
    assert str(result.total) in embed.description


def test_roll_card_collapses_title_for_many_groups():
    result = roll('+'.join(['d6'] * 25), rng=random.Random(7))
    embed = MessageWriter.roll_card(result, 'TestUser')
    assert len(embed.title) <= 256
    assert 'dice groups' in embed.title


# ---------------------------------------------------------------------------
# Markdown must render, so a breakdown with markup cannot sit in a code span
# ---------------------------------------------------------------------------

def _wod(faces, target=6, subtract_ones=True):
    class _Fixed(random.Random):
        def __init__(self):
            super().__init__()
            self._faces = list(faces)

        def randint(self, a, b):
            return self._faces.pop(0)

    return roll(f'{len(faces)}d10', target=target, subtract_ones=subtract_ones, rng=_Fixed())


def test_hit_breakdown_is_not_wrapped_in_backticks():
    """Discord renders nothing inside `code`, so bold hits would show as **8**."""
    embed = MessageWriter.roll_card(_wod([8, 1, 9, 2, 8]), 'TestUser')
    assert '`[' not in embed.description
    assert '**8**' in embed.description


def test_dropped_dice_breakdown_is_not_wrapped_in_backticks():
    result = roll('2d20', keep='high', rng=random.Random(2))
    embed = MessageWriter.roll_card(result, 'TestUser')
    assert '~~' in embed.description
    assert '`[' not in embed.description


def test_plain_sum_breakdown_keeps_its_code_span():
    result = roll('2d6+3', rng=random.Random(1))
    embed = MessageWriter.roll_card(result, 'TestUser')
    assert '`' in embed.description


def test_compact_breakdown_keeps_its_code_span():
    result = roll('300d20', rng=random.Random(5))
    embed = MessageWriter.roll_card(result, 'TestUser')
    assert '`300d20(' in embed.description
