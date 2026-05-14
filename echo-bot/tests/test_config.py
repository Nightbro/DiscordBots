from utils.config import (
    BOT_NAME,
    PREFIX,
    COLOR,
    EMOJI_YES,
    EMOJI_NO,
    EMOJI_MUSIC,
    EMOJI_SPEAKING,
    EMOJI_LOADING,
    PANEL_TIMEOUT,
    MAX_QUEUE,
    TTS_DEFAULT_VOICE,
    TTS_DEFAULT_RATE,
    DATA_DIR,
    DOWNLOADS_DIR,
    INTRO_SOUNDS_DIR,
    SOUNDBOARD_DIR,
    LOGS_DIR,
    PLAYLISTS_FILE,
    INTRO_CONFIG_FILE,
    SOUNDBOARD_CONFIG_FILE,
)


def test_bot_identity():
    assert BOT_NAME == 'Echo'
    assert PREFIX == '!'


def test_color_is_int():
    assert isinstance(COLOR, int)
    assert COLOR > 0


def test_emojis_are_nonempty_strings():
    for emoji in (EMOJI_YES, EMOJI_NO, EMOJI_MUSIC, EMOJI_SPEAKING, EMOJI_LOADING):
        assert isinstance(emoji, str)
        assert len(emoji) > 0


def test_audio_settings_are_positive_ints():
    assert isinstance(PANEL_TIMEOUT, int) and PANEL_TIMEOUT > 0
    assert isinstance(MAX_QUEUE, int) and MAX_QUEUE > 0


def test_tts_defaults_are_strings():
    assert isinstance(TTS_DEFAULT_VOICE, str) and TTS_DEFAULT_VOICE
    assert isinstance(TTS_DEFAULT_RATE, str) and TTS_DEFAULT_RATE


def test_data_dirs_exist():
    assert DATA_DIR.exists()
    assert DOWNLOADS_DIR.exists()
    assert INTRO_SOUNDS_DIR.exists()
    assert SOUNDBOARD_DIR.exists()
    assert LOGS_DIR.exists()


def test_data_dirs_are_under_data():
    for path in (DOWNLOADS_DIR, INTRO_SOUNDS_DIR, SOUNDBOARD_DIR, LOGS_DIR):
        assert DATA_DIR in path.parents


def test_json_paths_are_under_data():
    for path in (PLAYLISTS_FILE, INTRO_CONFIG_FILE, SOUNDBOARD_CONFIG_FILE):
        assert path.parent == DATA_DIR
        assert path.suffix == '.json'
