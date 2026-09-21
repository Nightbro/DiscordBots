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


def _fake_resp(body: bytes) -> MagicMock:
    resp = MagicMock()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.read.return_value = body
    return resp


def _suno_urlopen(uuid: str, *, clip: dict | None, ok_urls: set[str], captured: list[str]):
    """Fake urlopen: serves the clip API JSON and 'audio' bytes for ok_urls, 403s otherwise."""
    import json
    import urllib.error

    def fake(req, **_):
        url = req.full_url
        captured.append(url)
        if url == f'https://studio-api.prod.suno.com/api/clip/{uuid}':
            if clip is None:
                raise urllib.error.HTTPError(url, 404, 'Not Found', {}, None)
            return _fake_resp(json.dumps(clip).encode())
        if url in ok_urls:
            return _fake_resp(b'audio:' + url.encode())
        raise urllib.error.HTTPError(url, 403, 'Forbidden', {}, None)
    return fake


async def test_download_suno_uses_clip_api_media_url(tmp_path):
    """_download_suno downloads the m4a listed in the clip API's media_urls."""
    uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    track = Track(title='Suno Song', url=f'https://suno.com/song/{uuid}', source_id=uuid)
    m4a = f'https://d2lwuy8qc234o3.cloudfront.net/1/clip/{uuid}.m4a'
    clip = {
        'audio_url': 'https://studio-api.prod.suno.com/api/forbidden',
        'media_urls': [{'url': m4a, 'content_type': 'm4a-opus'}],
    }
    captured: list[str] = []

    with patch('utils.downloader.DOWNLOADS_DIR', tmp_path),          patch('utils.downloader.urllib.request.urlopen',
               side_effect=_suno_urlopen(uuid, clip=clip, ok_urls={m4a}, captured=captured)):
        result = await Downloader._download_suno(track)

    assert result == tmp_path / f'{uuid}.m4a'
    assert result.read_bytes() == b'audio:' + m4a.encode()
    assert track.file_path == result
    assert 'https://studio-api.prod.suno.com/api/forbidden' not in captured


async def test_download_suno_falls_back_to_legacy_cdn(tmp_path):
    """If the clip API fails, the legacy cdn1 mp3 URL is tried."""
    uuid = 'aaaaaaaa-bbbb-cccc-dddd-222222222222'
    track = Track(title='Suno', url=f'https://suno.com/song/{uuid}', source_id=uuid)
    legacy = f'https://cdn1.suno.ai/{uuid}.mp3'
    captured: list[str] = []

    with patch('utils.downloader.DOWNLOADS_DIR', tmp_path),          patch('utils.downloader.urllib.request.urlopen',
               side_effect=_suno_urlopen(uuid, clip=None, ok_urls={legacy}, captured=captured)):
        result = await Downloader._download_suno(track)

    assert result == tmp_path / f'{uuid}.mp3'
    assert captured[-1] == legacy


async def test_download_suno_raises_when_all_sources_fail(tmp_path):
    uuid = 'aaaaaaaa-bbbb-cccc-dddd-333333333333'
    track = Track(title='Suno', url=f'https://suno.com/song/{uuid}', source_id=uuid)

    with patch('utils.downloader.DOWNLOADS_DIR', tmp_path),          patch('utils.downloader.urllib.request.urlopen',
               side_effect=_suno_urlopen(uuid, clip={}, ok_urls=set(), captured=[])):
        with pytest.raises(RuntimeError, match=uuid):
            await Downloader._download_suno(track)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('ext', ['.mp3', '.m4a'])
async def test_download_suno_uses_cache(tmp_path, ext):
    """_download_suno returns cached file without hitting the network."""
    uuid = 'aaaaaaaa-bbbb-cccc-dddd-ffffffffffff'
    cached = tmp_path / f'{uuid}{ext}'
    cached.write_bytes(b'cached')
    track = Track(title='Suno', url=f'https://suno.com/song/{uuid}', source_id=uuid)

    with patch('utils.downloader.DOWNLOADS_DIR', tmp_path),          patch('utils.downloader.urllib.request.urlopen') as mock_open:
        result = await Downloader._download_suno(track)

    mock_open.assert_not_called()
    assert result == cached


@pytest.mark.parametrize('suffix', ['?sh=abc123XYZ', '-1'])
async def test_download_suno_cleans_source_id(tmp_path, suffix):
    """yt-dlp source_ids like 'uuid?sh=..' or 'uuid-1' resolve to the bare UUID."""
    uuid = 'aaaaaaaa-bbbb-cccc-dddd-111111111111'
    track = Track(title='Suno', url=f'https://suno.com/song/{uuid}', source_id=uuid + suffix)
    legacy = f'https://cdn1.suno.ai/{uuid}.mp3'
    legacy_url = f'{legacy}?sh=abc123XYZ' if suffix.startswith('?') else legacy
    captured: list[str] = []

    with patch('utils.downloader.DOWNLOADS_DIR', tmp_path),          patch('utils.downloader.urllib.request.urlopen',
               side_effect=_suno_urlopen(uuid, clip=None, ok_urls={legacy_url}, captured=captured)):
        result = await Downloader._download_suno(track)

    assert captured[0] == f'https://studio-api.prod.suno.com/api/clip/{uuid}'
    assert captured[-1] == legacy_url
    assert result == tmp_path / f'{uuid}.mp3'


async def test_download_routes_suno_to_download_suno():
    """download() calls _download_suno for Suno URLs instead of yt-dlp."""
    uuid = 'aaaaaaaa-bbbb-cccc-dddd-000000000000'
    # No source_id so the generic cache check in download() is skipped
    track = Track(title='Suno', url=f'https://suno.com/song/{uuid}')
    fake_path = Path('/fake/uuid.mp3')
    with patch.object(Downloader, '_download_suno', new=AsyncMock(return_value=fake_path)) as mock_suno, \
         patch.object(Downloader, '_ydl_download') as mock_ydl:
        result = await Downloader.download(track)
    mock_suno.assert_awaited_once()
    mock_ydl.assert_not_called()
    assert result == fake_path


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
