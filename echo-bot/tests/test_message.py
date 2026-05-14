import pytest
import discord

from utils.config import BOT_NAME, COLOR
from utils.guild_state import Track
from utils.message import MessageWriter, _GREEN, _RED


def test_success_color():
    e = MessageWriter.success('Done')
    assert e.color.value == _GREEN


def test_error_color():
    e = MessageWriter.error('Failed')
    assert e.color.value == _RED


def test_info_color():
    e = MessageWriter.info('Note')
    assert e.color.value == COLOR


def test_success_title_contains_text():
    e = MessageWriter.success('Track added')
    assert 'Track added' in e.title


def test_error_title_contains_text():
    e = MessageWriter.error('No voice channel')
    assert 'No voice channel' in e.title


def test_description_set_when_provided():
    e = MessageWriter.success('Done', 'All good')
    assert e.description == 'All good'


def test_description_empty_when_omitted():
    e = MessageWriter.info('Title')
    assert not e.description


def test_footer_contains_bot_name():
    for embed in (
        MessageWriter.success('a'),
        MessageWriter.error('b'),
        MessageWriter.info('c'),
    ):
        assert embed.footer.text == BOT_NAME


def test_track_card_title():
    track = Track(title='My Song', url='https://example.com')
    e = MessageWriter.track_card(track)
    assert 'My Song' in e.title


def test_track_card_duration_field():
    track = Track(title='T', url='u', duration=90)
    e = MessageWriter.track_card(track)
    assert any(f.value == '1:30' for f in e.fields)


def test_track_card_duration_zero_pad():
    track = Track(title='T', url='u', duration=65)
    e = MessageWriter.track_card(track)
    assert any(f.value == '1:05' for f in e.fields)


def test_track_card_no_duration_when_none():
    track = Track(title='T', url='u')
    e = MessageWriter.track_card(track)
    assert not any(f.name == 'Duration' for f in e.fields)


def test_track_card_requester_field(ctx):
    track = Track(title='T', url='u', requester=ctx.author)
    e = MessageWriter.track_card(track)
    assert any(f.name == 'Requested by' for f in e.fields)


def test_queue_page_empty():
    e = MessageWriter.queue_page([], 1, 1)
    assert 'empty' in e.description.lower()


def test_queue_page_numbering():
    tracks = [Track(title=f'Song {i}', url='u') for i in range(3)]
    e = MessageWriter.queue_page(tracks, 1, 1)
    assert '**1.** Song 0' in e.description
    assert '**3.** Song 2' in e.description


def test_queue_page_second_page_offset():
    tracks = [Track(title=f'S{i}', url='u') for i in range(3)]
    e = MessageWriter.queue_page(tracks, 2, 3)
    assert '**11.** S0' in e.description


def test_soundboard_panel_with_sounds():
    sounds = {
        'boom': {'emoji': '💥', 'file': 'boom.mp3'},
        'airhorn': {'emoji': '📯', 'file': 'airhorn.mp3'},
    }
    e = MessageWriter.soundboard_panel(sounds)
    assert 'boom' in e.description
    assert 'airhorn' in e.description


def test_soundboard_panel_empty():
    e = MessageWriter.soundboard_panel({})
    assert 'No sounds' in e.description
