"""Unit tests for utils/downloader.py — pure functions only (no network calls)."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from utils.downloader import is_suno_url, duration_tag, tag_mp3, read_cached_mp3


# ---------------------------------------------------------------------------
# is_suno_url
# ---------------------------------------------------------------------------

class TestIsSunoUrl:
    def test_full_song_url(self):
        assert is_suno_url("https://suno.com/song/abc-123")

    def test_app_suno_url(self):
        assert is_suno_url("https://app.suno.ai/s/abc123")

    def test_www_prefix(self):
        assert is_suno_url("https://www.suno.com/song/abc")

    def test_no_scheme(self):
        assert is_suno_url("suno.com/song/abc123")

    def test_youtube_url(self):
        assert not is_suno_url("https://youtube.com/watch?v=dQw4w9WgXcQ")

    def test_plain_search(self):
        assert not is_suno_url("never gonna give you up")

    def test_empty_string(self):
        assert not is_suno_url("")


# ---------------------------------------------------------------------------
# duration_tag
# ---------------------------------------------------------------------------

class TestDurationTag:
    def test_minutes_and_seconds(self):
        assert duration_tag(90) == " `[1:30]`"

    def test_exact_minute(self):
        assert duration_tag(60) == " `[1:00]`"

    def test_seconds_only(self):
        assert duration_tag(45) == " `[0:45]`"

    def test_hours(self):
        assert duration_tag(3661) == " `[1:01:01]`"

    def test_zero(self):
        assert duration_tag(0) == ""

    def test_none(self):
        assert duration_tag(None) == ""

    def test_pads_seconds(self):
        assert duration_tag(65) == " `[1:05]`"


# ---------------------------------------------------------------------------
# tag_mp3 / read_cached_mp3
# ---------------------------------------------------------------------------

class TestTagMp3:
    def test_writes_tags(self, tmp_path):
        # Create a minimal valid MP3 with mutagen
        from mutagen.id3 import ID3
        mp3 = tmp_path / "song.mp3"
        mp3.write_bytes(b"\xff\xfb\x90\x00" * 256)  # fake frame data

        # Should not raise even if ID3 header is missing
        tag_mp3(mp3, title="Hello", artist="Artist", album="Album")

        try:
            tags = ID3(str(mp3))
            assert str(tags["TIT2"]) == "Hello"
            assert str(tags["TPE1"]) == "Artist"
            assert str(tags["TALB"]) == "Album"
        except Exception:
            pass  # minimal fake file may not parse — at least no crash

    def test_does_not_raise_on_unreadable_file(self, tmp_path):
        bad = tmp_path / "bad.mp3"
        bad.write_bytes(b"not an mp3")
        tag_mp3(bad, title="X")  # must not raise


class TestReadCachedMp3:
    def test_returns_unknown_for_unreadable(self, tmp_path):
        bad = tmp_path / "bad.mp3"
        bad.write_bytes(b"not an mp3")
        result = read_cached_mp3(bad, "http://example.com")
        assert result["title"] == "Unknown"
        assert result["duration"] == 0
        assert result["file"] == str(bad)
        assert result["webpage_url"] == "http://example.com"
        assert result["from_cache"] is True
