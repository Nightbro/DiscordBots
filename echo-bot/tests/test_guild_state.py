from collections import deque
from pathlib import Path

from utils.config import TTS_DEFAULT_VOICE
from utils.guild_state import GuildState, Track


def test_guild_state_defaults():
    state = GuildState()
    assert isinstance(state.queue, deque)
    assert len(state.queue) == 0
    assert state.voice_client is None
    assert state.current_track is None
    assert state.interrupted_track is None
    assert isinstance(state.tts_queue, deque)
    assert state.tts_voice == TTS_DEFAULT_VOICE
    assert state.soundboard_panel_message is None


def test_guild_states_are_independent():
    a = GuildState()
    b = GuildState()
    track = Track(title='X', url='https://example.com')
    a.queue.append(track)
    assert len(b.queue) == 0


def test_track_required_fields():
    track = Track(title='My Song', url='https://example.com/song')
    assert track.title == 'My Song'
    assert track.url == 'https://example.com/song'


def test_track_optional_fields_default_none():
    track = Track(title='T', url='u')
    assert track.file_path is None
    assert track.duration is None
    assert track.requester is None


def test_track_with_all_fields():
    path = Path('/tmp/song.mp3')
    track = Track(title='T', url='u', file_path=path, duration=180)
    assert track.file_path == path
    assert track.duration == 180


def test_guild_state_queue_operations():
    state = GuildState()
    t1 = Track(title='First', url='u1')
    t2 = Track(title='Second', url='u2')
    state.queue.append(t1)
    state.queue.append(t2)
    assert len(state.queue) == 2
    assert state.queue.popleft().title == 'First'
    assert len(state.queue) == 1


def test_guild_state_tts_voice_mutable():
    state = GuildState()
    state.tts_voice = 'en-GB-RyanNeural'
    assert state.tts_voice == 'en-GB-RyanNeural'
    other = GuildState()
    assert other.tts_voice == TTS_DEFAULT_VOICE
