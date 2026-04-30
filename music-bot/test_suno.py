"""
Suno-bot diagnostic tests.

Usage:
    python test_suno.py                              # uses built-in test URL
    python test_suno.py https://suno.com/song/<id>   # test your own Suno URL
"""

import sys
import re
import urllib.request
import urllib.error

# ── SSL fix (same as bot.py) ──────────────────────────────────────────────────
import ssl, certifi
ssl.create_default_context = lambda purpose=ssl.Purpose.SERVER_AUTH, **kw: (
    lambda ctx: (ctx.load_verify_locations(certifi.where()), ctx)[1]
)(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
# ─────────────────────────────────────────────────────────────────────────────

SUNO_RE = re.compile(
    r'(?:https?://)?(?:www\.)?(?:suno\.com|app\.suno\.ai)/(?:song|s)/([a-zA-Z0-9-]+)'
)
SUNO_UUID_RE = re.compile(r'/song/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})')

# Replace with any public Suno song URL to test with your own content
DEFAULT_TEST_URL = 'https://suno.com/s/Wo6HCILgAp6NIYoT'

GREEN = '\033[92m'
RED   = '\033[91m'
RESET = '\033[0m'

_results: list[bool] = []


def check(label: str, passed: bool, detail: str = '') -> bool:
    mark = f'{GREEN}PASS{RESET}' if passed else f'{RED}FAIL{RESET}'
    print(f'  [{mark}] {label}' + (f'  ({detail})' if detail else ''))
    _results.append(passed)
    return passed


def head(url: str, timeout: int = 10) -> tuple[int, str]:
    """Return (status_code, content_type) for a HEAD request, or (-1, error)."""
    try:
        req = urllib.request.Request(url, method='HEAD',
                                     headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception as e:
        return -1, str(e)


# ─── Test suites ─────────────────────────────────────────────────────────────

def test_url_detection():
    print('\n── 1. URL Detection ──────────────────────────────')
    cases = [
        ('https://suno.com/song/abc123',                 True),
        ('https://www.suno.com/song/abc-def-456',        True),
        ('https://app.suno.ai/song/xyz',                 True),
        ('suno.com/song/no-scheme',                      True),
        ('https://suno.com/s/Wo6HCILgAp6NIYoT',         True),   # short URL
        ('https://suno.com/s/abc123',                    True),   # short URL
        ('https://youtube.com/watch?v=abc',              False),
        ('lo-fi hip hop',                                False),
        ('https://soundcloud.com/track/something',       False),
    ]
    for url, expected in cases:
        got = bool(SUNO_RE.search(url))
        check(url[:55], got == expected,
              f'expected={expected}  got={got}')


def test_id_extraction():
    print('\n── 2. Song ID Extraction ─────────────────────────')
    cases = [
        ('https://suno.com/song/7b6f6888-3a57-49b6-adb4-a5a3e56d8e33',
         '7b6f6888-3a57-49b6-adb4-a5a3e56d8e33'),
        ('https://app.suno.ai/song/abc123', 'abc123'),
    ]
    for url, expected_id in cases:
        m = SUNO_RE.search(url)
        got = m.group(1) if m else None
        check(url[:55], got == expected_id, f'id={got}')


def test_cdn_url(song_id: str):
    print(f'\n── 3. CDN URL Accessibility ──────────────────────')
    cdn_url = f'https://cdn1.suno.ai/{song_id}.mp3'
    print(f'  URL: {cdn_url}')
    status, ct = head(cdn_url)
    check('CDN responds 200', status == 200, f'status={status}  content-type={ct}')
    if status == 200:
        check('Content-Type is audio', 'audio' in ct or 'octet' in ct, ct)


def test_yt_dlp_suno(url: str):
    print(f'\n── 4. yt-dlp Suno Extraction + UUID Resolution ──')
    try:
        import yt_dlp
    except ImportError:
        check('yt-dlp installed', False, 'pip install yt-dlp')
        return

    opts = {'format': 'bestaudio/best', 'quiet': True, 'noplaylist': True}
    song_uuid = None
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                info = info['entries'][0]

        title      = info.get('title', '')
        ydl_url    = info.get('url', '')
        duration   = info.get('duration')
        raw_id     = info.get('id', '')
        webpage_url = info.get('webpage_url', '')

        check('Title extracted',   bool(title),    f'title={title!r}')
        check('Duration returned', duration is not None, f'duration={duration}s')
        check('Audio URL returned', bool(ydl_url),
              (ydl_url[:70] + '…') if len(ydl_url) > 70 else ydl_url)

        # Resolve song UUID (needed for CDN)
        if re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', raw_id):
            song_uuid = raw_id
        else:
            m = SUNO_UUID_RE.search(webpage_url)
            if m:
                song_uuid = m.group(1)

        check('Song UUID resolved', bool(song_uuid), f'uuid={song_uuid}')

        if ydl_url:
            print('  Checking if yt-dlp URL is directly streamable...')
            status, ct = head(ydl_url)
            accessible = status == 200
            check('yt-dlp URL accessible', accessible,
                  f'status={status}  content-type={ct}')
            if not accessible:
                print('  NOTE: yt-dlp URL is not directly streamable — expected.')
                print('        The bot uses cdn1.suno.ai/<uuid>.mp3 instead.')

    except Exception as e:
        check('yt-dlp extraction', False, str(e))

    # Confirm the CDN URL (what the fixed bot uses) is reachable
    if song_uuid:
        print()
        cdn_url = f'https://cdn1.suno.ai/{song_uuid}.mp3'
        status, ct = head(cdn_url)
        check('CDN URL accessible (what bot streams)', status == 200,
              f'status={status}  url={cdn_url}')


def test_youtube_search():
    print('\n── 5. YouTube Search ─────────────────────────────')
    try:
        import yt_dlp
    except ImportError:
        check('yt-dlp installed', False, 'pip install yt-dlp')
        return

    opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
        'default_search': 'ytsearch',
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info('lo-fi hip hop', download=False)
            if 'entries' in info:
                info = info['entries'][0]
        check('Search returns result', bool(info.get('title')),
              f'title={info.get("title", "")!r}')
        check('Audio URL present', bool(info.get('url')))
    except Exception as e:
        check('YouTube search', False, str(e))


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    test_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TEST_URL

    print('=' * 52)
    print('  suno-bot diagnostics')
    print(f'  Suno URL: {test_url}')
    print('=' * 52)

    test_url_detection()
    test_id_extraction()

    if SUNO_RE.search(test_url):
        # CDN test only makes sense for /song/<uuid> URLs; skip for short URLs
        # (UUID is resolved at runtime via yt-dlp)
        uuid_match = SUNO_UUID_RE.search(test_url)
        if uuid_match:
            test_cdn_url(uuid_match.group(1))
        else:
            print('\n── 3. CDN URL Accessibility ──────────────────────')
            print('  (skipped — short URL; UUID resolved dynamically in test 4)')
        test_yt_dlp_suno(test_url)
    else:
        print(f'\n[!] "{test_url}" is not a valid Suno URL — skipping CDN/yt-dlp tests.')

    test_youtube_search()

    passed = sum(_results)
    total  = len(_results)
    print('\n' + '=' * 52)
    print(f'  {passed}/{total} passed', end='')
    if passed == total:
        print(f'  {GREEN}All good!{RESET}')
    else:
        print(f'  {RED}{total - passed} failed{RESET}')
    print('=' * 52)
    sys.exit(0 if passed == total else 1)
