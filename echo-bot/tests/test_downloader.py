import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from utils.downloader import Downloader
from utils.guild_state import Track


# ---------------------------------------------------------------------------
# is_suno_url
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('url', [
    'https://suno.com/song/abc',
    'https://www.suno.com/song/abc',
    'http://suno.ai/song/abc',
    'https://www.suno.ai/track/xyz',
])
def test_is_suno_url_positive(url):
    assert Downloader.is_suno_url(url) is True


@pytest.mark.parametrize('url', [
    'https://www.youtube.com/watch?v=abc',
    'https://soundcloud.com/artist/track',
    'https://open.spotify.com/track/abc',
    'not-a-url',
    '',
])
def test_is_suno_url_negative(url):
    assert Downloader.is_suno_url(url) is False


# ---------------------------------------------------------------------------
# resolve — routing
# ---------------------------------------------------------------------------

async def test_resolve_dispatches_url_to_resolve_url():
    with patch.object(Downloader, '_resolve_url', new=AsyncMock(
        return_value=Track(title='T', url='https://youtube.com/watch?v=x')
    )) as mock:
        track = await Downloader.resolve('https://youtube.com/watch?v=x')
    mock.assert_awaited_once()
    assert track.title == 'T'


async def test_resolve_dispatches_search_query():
    with patch.object(Downloader, '_resolve_search', new=AsyncMock(
        return_value=Track(title='Result', url='https://youtube.com/watch?v=r')
    )) as mock:
        track = await Downloader.resolve('never gonna give you up')
    mock.assert_awaited_once()
    assert track.title == 'Result'


async def test_resolve_suno_url_goes_to_resolve_url():
    with patch.object(Downloader, '_resolve_url', new=AsyncMock(
        return_value=Track(title='Suno', url='https://suno.com/song/abc')
    )) as mock:
        await Downloader.resolve('https://suno.com/song/abc')
    mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# download — caching
# ---------------------------------------------------------------------------

async def test_download_returns_existing_file_path(tmp_path):
    local = tmp_path / 'song.mp3'
    local.write_bytes(b'audio')
    track = Track(title='T', url='u', file_path=local)
    result = await Downloader.download(track)
    assert result == local


async def test_download_uses_source_id_cache(tmp_path):
    from utils import config as cfg
    cached = tmp_path / 'abc123.mp3'
    cached.write_bytes(b'audio')

    track = Track(title='T', url='u', source_id='abc123')

    with patch.object(cfg, 'DOWNLOADS_DIR', tmp_path):
        # Re-import to pick up patched constant in downloader
        import importlib
        import utils.downloader as dl_module
        importlib.reload(dl_module)
        from utils.downloader import Downloader as D

        result = await D.download(track)

    assert result == cached
    assert track.file_path == cached


async def test_download_calls_ydl_when_no_cache(tmp_path):
    # Verify that download() invokes yt-dlp when there is no cache hit.
    # Mock yt_dlp.YoutubeDL to avoid a real network call; the static method
    # runs in an executor thread so class-level patches don't reach it reliably.
    track = Track(title='T', url='https://example.com/fake', source_id='nocache')
    fake_mp3 = tmp_path / 'nocache.mp3'
    fake_mp3.write_bytes(b'')

    fake_info = {'id': 'nocache', 'title': 'Test', 'ext': 'mp3'}
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info = MagicMock(return_value=fake_info)
    mock_ydl.prepare_filename = MagicMock(return_value=str(tmp_path / 'nocache.mp3'))

    with patch('utils.downloader.DOWNLOADS_DIR', Path('/nonexistent')):
        with patch('utils.downloader.yt_dlp.YoutubeDL', return_value=mock_ydl):
            result = await Downloader.download(track)

    assert result == fake_mp3
    assert track.file_path == fake_mp3


# ---------------------------------------------------------------------------
# _ydl_info / _ydl_download — unit (mocked yt_dlp)
# ---------------------------------------------------------------------------

def test_ydl_info_calls_extract_info():
    fake_info = {'id': 'abc', 'title': 'Test', 'duration': 120}
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info = MagicMock(return_value=fake_info)

    with patch('utils.downloader.yt_dlp.YoutubeDL', return_value=mock_ydl):
        result = Downloader._ydl_info('https://youtube.com/watch?v=abc')

    assert result == fake_info
    mock_ydl.extract_info.assert_called_once_with('https://youtube.com/watch?v=abc', download=False)


def test_ydl_download_returns_mp3_path(tmp_path):
    mp3 = tmp_path / 'abc.mp3'
    mp3.write_bytes(b'')

    fake_info = {'id': 'abc', 'title': 'Test', 'ext': 'webm'}
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info = MagicMock(return_value=fake_info)
    mock_ydl.prepare_filename = MagicMock(return_value=str(tmp_path / 'abc.webm'))

    with patch('utils.downloader.yt_dlp.YoutubeDL', return_value=mock_ydl):
        result = Downloader._ydl_download('https://youtube.com/watch?v=abc')

    assert result == mp3


def test_ydl_download_falls_back_to_original_ext(tmp_path):
    # mp3 doesn't exist, falls back to original filename
    webm = tmp_path / 'abc.webm'
    webm.write_bytes(b'')

    fake_info = {'id': 'abc', 'title': 'Test', 'ext': 'webm'}
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info = MagicMock(return_value=fake_info)
    mock_ydl.prepare_filename = MagicMock(return_value=str(webm))

    with patch('utils.downloader.yt_dlp.YoutubeDL', return_value=mock_ydl):
        result = Downloader._ydl_download('https://youtube.com/watch?v=abc')

    assert result == webm
