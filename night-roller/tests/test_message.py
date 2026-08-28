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
