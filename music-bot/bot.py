# ── SSL fix: must be FIRST before any other imports ──────────────────────────
import ssl
import certifi

def _patched_ssl_context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None, **_):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(cafile or certifi.where(), capath, cadata)
    return ctx

ssl.create_default_context = _patched_ssl_context

# Pre-built context used for direct urllib calls — bypasses the monkey-patch
# so it works even when internal callers pass unexpected keyword args.
_SSL_CTX = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_SSL_CTX.load_verify_locations(certifi.where())
# ─────────────────────────────────────────────────────────────────────────────

import os
import re
import json
import asyncio
import logging
import urllib.request
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

import discord
from discord.ext import commands
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, ID3NoHeaderError
from dotenv import load_dotenv

# --- Paths ---
BASE_DIR       = Path(__file__).parent
DOWNLOADS_DIR  = BASE_DIR / 'downloads'
LOGS_DIR       = BASE_DIR / 'logs'
PLAYLISTS_FILE = BASE_DIR / 'playlists.json'
DOWNLOADS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# --- Logging ---
_fmt = logging.Formatter(
    fmt='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

_file_handler = RotatingFileHandler(
    LOGS_DIR / 'music-bot.log',
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding='utf-8',
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(_fmt)

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(_fmt)

logging.basicConfig(level=logging.DEBUG, handlers=[_file_handler, _console_handler])
logging.getLogger('discord').setLevel(logging.WARNING)
logging.getLogger('discord.http').setLevel(logging.WARNING)

log = logging.getLogger('music-bot')

# --- URL patterns ---
SUNO_RE = re.compile(
    r'(?:https?://)?(?:www\.)?(?:suno\.com|app\.suno\.ai)/(?:song|s)/([a-zA-Z0-9-]+)'
)
SUNO_UUID_RE = re.compile(
    r'/song/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
)
YOUTUBE_ID_RE = re.compile(
    r'(?:youtube\.com/(?:watch\?.*?v=|shorts/)|youtu\.be/)([a-zA-Z0-9_-]{11})'
)

# --- yt-dlp options ---
class _YDLLogger:
    def debug(self, msg):
        if not msg.startswith('[debug] '):
            log.debug('yt-dlp: %s', msg)
    def info(self, msg):
        log.info('yt-dlp: %s', msg)
    def warning(self, msg):
        log.warning('yt-dlp: %s', msg)
    def error(self, msg):
        log.error('yt-dlp: %s', msg)

YDL_INFO = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'logger': _YDLLogger(),
    'default_search': 'ytsearch',
}

# Download + convert to MP3 + embed title/artist/album tags
YDL_DOWNLOAD = {
    **YDL_INFO,
    'outtmpl': str(DOWNLOADS_DIR / '%(id)s.%(ext)s'),
    'postprocessors': [
        {
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        },
        {
            'key': 'FFmpegMetadata',
            'add_metadata': True,
        },
    ],
}

# Local file playback — no reconnect flags needed
FFMPEG_OPTIONS = {'options': '-vn'}

# --- Bot setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

guilds: dict = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_state(guild_id: int) -> dict:
    if guild_id not in guilds:
        guilds[guild_id] = {'queue': deque(), 'voice_client': None}
    return guilds[guild_id]


async def ensure_voice(ctx: commands.Context) -> bool:
    if not ctx.author.voice:
        await ctx.send('You need to be in a voice channel.')
        return False
    channel = ctx.author.voice.channel
    state = get_state(ctx.guild.id)
    vc = state['voice_client']
    if vc is None or not vc.is_connected():
        state['voice_client'] = await channel.connect()
    elif vc.channel != channel:
        await vc.move_to(channel)
    return True


def is_suno_url(query: str) -> bool:
    return bool(SUNO_RE.search(query))


def duration_tag(seconds) -> str:
    """Returns ' `[M:SS]`' or '' when duration is unknown."""
    if not seconds:
        return ''
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    t = f'{h}:{m:02}:{s:02}' if h else f'{m}:{s:02}'
    return f' `[{t}]`'


# ── Download logic ────────────────────────────────────────────────────────────

def tag_mp3(path: Path, title: str, artist: str = 'Suno AI', album: str = 'Suno'):
    try:
        try:
            tags = ID3(str(path))
        except ID3NoHeaderError:
            tags = ID3()
        tags['TIT2'] = TIT2(encoding=3, text=title)
        tags['TPE1'] = TPE1(encoding=3, text=artist)
        tags['TALB'] = TALB(encoding=3, text=album)
        tags.save(str(path))
    except Exception as e:
        log.warning('Could not write ID3 tags to %s: %s', path.name, e)


def read_cached_mp3(path: Path, webpage_url: str = '') -> dict:
    """Build a track dict from an already-cached MP3 using its ID3 tags."""
    title = 'Unknown'
    duration = 0
    try:
        audio = MP3(str(path))
        duration = int(audio.info.length)
    except Exception:
        pass
    try:
        tags = ID3(str(path))
        if 'TIT2' in tags:
            title = str(tags['TIT2'])
    except Exception:
        pass
    log.debug('Cache hit: %s (%s)', title, path.name)
    return {
        'file': str(path),
        'title': title,
        'duration': duration,
        'webpage_url': webpage_url,
        'from_cache': True,
    }


def download_youtube(query: str) -> dict:
    # Fast path: direct YouTube URL whose ID we can extract without a network call
    m = YOUTUBE_ID_RE.search(query)
    if m:
        cached = DOWNLOADS_DIR / f'{m.group(1)}.mp3'
        if cached.exists():
            return read_cached_mp3(cached, query)

    # Need network: search query, or direct URL not yet cached
    log.info('Fetching info for: %s', query)
    with yt_dlp.YoutubeDL(YDL_INFO) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info:
            info = info['entries'][0]

    video_id   = info['id']
    title      = info.get('title', 'Unknown')
    duration   = info.get('duration', 0)
    source_url = info.get('webpage_url', query)
    cached     = DOWNLOADS_DIR / f'{video_id}.mp3'

    if cached.exists():
        track = read_cached_mp3(cached, source_url)
        track['title'] = title
        track['duration'] = duration
        return track

    log.info('Downloading: %s', title)
    with yt_dlp.YoutubeDL(YDL_DOWNLOAD) as ydl:
        ydl.extract_info(source_url, download=True)
    log.info('Download complete: %s', title)

    return {
        'file': str(cached),
        'title': title,
        'duration': duration,
        'webpage_url': source_url,
        'from_cache': False,
    }


def download_suno(url: str) -> dict:
    # Fast path: UUID is already in the URL (full /song/<uuid> links)
    m = SUNO_UUID_RE.search(url)
    if m:
        cached = DOWNLOADS_DIR / f'{m.group(1)}.mp3'
        if cached.exists():
            track = read_cached_mp3(cached, url)
            track.setdefault('artist', 'Suno AI')
            return track

    # Need to resolve UUID via yt-dlp (short /s/<id> links)
    title     = 'Unknown Suno Track'
    artist    = 'Suno AI'
    duration  = 0
    song_uuid = None

    log.info('Resolving Suno URL: %s', url)
    try:
        with yt_dlp.YoutubeDL(YDL_INFO) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                info = info['entries'][0]
        title    = info.get('title', title)
        artist   = info.get('uploader') or info.get('creator') or artist
        duration = info.get('duration') or 0
        raw_id   = info.get('id', '')
        if re.fullmatch(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', raw_id
        ):
            song_uuid = raw_id
        else:
            m2 = SUNO_UUID_RE.search(info.get('webpage_url', ''))
            if m2:
                song_uuid = m2.group(1)
    except Exception as e:
        log.warning('yt-dlp could not resolve Suno URL (%s), falling back to URL parse', e)

    if not song_uuid:
        m2 = SUNO_UUID_RE.search(url)
        if m2:
            song_uuid = m2.group(1)

    if not song_uuid:
        raise ValueError(
            f'Could not resolve Suno song UUID from: {url}\n'
            'Make sure the song is public and the URL is correct.'
        )

    cached = DOWNLOADS_DIR / f'{song_uuid}.mp3'

    if cached.exists():
        track = read_cached_mp3(cached, url)
        track['artist'] = artist
        return track

    log.info('Downloading Suno track: %s (%s)', title, song_uuid)
    cdn_url = f'https://cdn1.suno.ai/{song_uuid}.mp3'
    req = urllib.request.Request(cdn_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as resp:
        cached.write_bytes(resp.read())
    tag_mp3(cached, title=title, artist=artist)
    log.info('Download complete: %s', title)

    return {
        'file': str(cached),
        'title': title,
        'artist': artist,
        'duration': duration,
        'webpage_url': url,
        'from_cache': False,
    }


def download_track(query: str) -> dict:
    """Entry point — routes to Suno or YouTube downloader."""
    if is_suno_url(query):
        return download_suno(query)
    return download_youtube(query)


# ── Playback ──────────────────────────────────────────────────────────────────

async def play_next(guild_id: int, channel: discord.TextChannel):
    state = get_state(guild_id)
    vc: discord.VoiceClient = state['voice_client']

    if not state['queue']:
        await channel.send('Queue finished. Use `!play` to add more songs.')
        return

    track = state['queue'].popleft()

    # Playlist tracks loaded from JSON don't have a local file yet — download now
    if not track.get('file') or not Path(track['file']).exists():
        await channel.send(f'Downloading **{track["title"]}**...')
        try:
            loop = asyncio.get_event_loop()
            track = await loop.run_in_executor(None, download_track, track['webpage_url'])
        except Exception as e:
            log.error('Failed to download playlist track "%s": %s', track.get('title'), e, exc_info=True)
            await channel.send(f'Failed to download track: `{e}` — skipping.')
            await play_next(guild_id, channel)
            return

    source = discord.FFmpegPCMAudio(track['file'], **FFMPEG_OPTIONS)

    def after(error):
        if error:
            log.error('Player error in guild %s: %s', guild_id, error, exc_info=error)
        asyncio.run_coroutine_threadsafe(play_next(guild_id, channel), bot.loop)

    vc.play(source, after=after)
    log.info('Now playing in guild %s: %s', guild_id, track["title"])
    await channel.send(f'Now playing: **{track["title"]}**{duration_tag(track["duration"])}')


# ── Playlist persistence ──────────────────────────────────────────────────────

def load_playlists() -> dict:
    if PLAYLISTS_FILE.exists():
        return json.loads(PLAYLISTS_FILE.read_text(encoding='utf-8'))
    return {}


def save_playlists(data: dict):
    PLAYLISTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def track_to_storable(track: dict) -> dict:
    """Strip the local file path before saving — paths may change across restarts."""
    return {k: v for k, v in track.items() if k not in ('file', 'from_cache')}


# ═══════════════════════════════════════════════════════════════════
#  Playback commands
# ═══════════════════════════════════════════════════════════════════

@bot.command(name='play', aliases=['p'])
async def play(ctx: commands.Context, *, query: str):
    """Play a YouTube URL/search or Suno song URL. Queues if something is playing."""
    if not await ensure_voice(ctx):
        return

    log.info('Play request from %s in guild %s: %r', ctx.author, ctx.guild.id, query)
    label = 'Suno track' if is_suno_url(query) else f'`{query}`'
    await ctx.send(f'Loading {label}...')

    try:
        loop = asyncio.get_event_loop()
        track = await loop.run_in_executor(None, download_track, query)
    except Exception as e:
        log.error('Download failed for %r: %s', query, e, exc_info=True)
        return await ctx.send(f'Could not download: `{e}`')

    state = get_state(ctx.guild.id)
    state['queue'].append(track)
    if state['voice_client'].is_playing() or state['voice_client'].is_paused():
        cache_note = ' *(cached)*' if track.get('from_cache') else ''
        await ctx.send(
            f'Added to queue: **{track["title"]}**{duration_tag(track["duration"])}'
            f'{cache_note} (#{len(state["queue"])})'
        )
    else:
        await play_next(ctx.guild.id, ctx.channel)


@bot.command(name='skip', aliases=['s'])
async def skip(ctx: commands.Context):
    """Skip the current song."""
    state = get_state(ctx.guild.id)
    vc = state['voice_client']
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send('Skipped.')
    else:
        await ctx.send('Nothing is playing.')


@bot.command(name='pause')
async def pause(ctx: commands.Context):
    """Pause playback."""
    state = get_state(ctx.guild.id)
    vc = state['voice_client']
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send('Paused.')
    else:
        await ctx.send('Nothing is playing.')


@bot.command(name='resume', aliases=['r'])
async def resume(ctx: commands.Context):
    """Resume paused playback."""
    state = get_state(ctx.guild.id)
    vc = state['voice_client']
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send('Resumed.')
    else:
        await ctx.send('Nothing is paused.')


@bot.command(name='stop')
async def stop(ctx: commands.Context):
    """Stop playback, clear queue, and disconnect."""
    state = get_state(ctx.guild.id)
    state['queue'].clear()
    vc = state['voice_client']
    if vc:
        vc.stop()
        await vc.disconnect()
        state['voice_client'] = None
    await ctx.send('Stopped and disconnected.')


@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx: commands.Context):
    """Show the current playback queue."""
    state = get_state(ctx.guild.id)
    if not state['queue']:
        return await ctx.send('The queue is empty.')
    lines = [
        f'`{i}.` **{t["title"]}**{duration_tag(t["duration"])}'
        for i, t in enumerate(state['queue'], 1)
    ]
    await ctx.send('**Queue:**\n' + '\n'.join(lines))


@bot.command(name='clear')
async def clear(ctx: commands.Context):
    """Clear the queue without stopping the current song."""
    get_state(ctx.guild.id)['queue'].clear()
    await ctx.send('Queue cleared.')


@bot.command(name='leave', aliases=['dc'])
async def leave(ctx: commands.Context):
    """Disconnect from voice."""
    state = get_state(ctx.guild.id)
    vc = state['voice_client']
    if vc and vc.is_connected():
        state['queue'].clear()
        await vc.disconnect()
        state['voice_client'] = None
        await ctx.send('Disconnected.')
    else:
        await ctx.send('Not connected to a voice channel.')


@bot.command(name='cleanup')
async def cleanup(ctx: commands.Context):
    """Delete all cached downloads to free up disk space."""
    files = list(DOWNLOADS_DIR.glob('*.mp3'))
    for f in files:
        f.unlink(missing_ok=True)
    log.info('Cleanup: deleted %d cached file(s) (requested by %s)', len(files), ctx.author)
    await ctx.send(f'Deleted {len(files)} cached file(s).')


# ═══════════════════════════════════════════════════════════════════
#  Playlist library  (!playlist / !pl)
# ═══════════════════════════════════════════════════════════════════

@bot.group(name='playlist', aliases=['pl'], invoke_without_command=True)
async def playlist_group(ctx: commands.Context):
    await ctx.send(
        '**Playlist commands:**\n'
        '`!pl save <name>` — save current queue as a playlist\n'
        '`!pl load <name>` — load playlist into queue\n'
        '`!pl list` — list all saved playlists\n'
        '`!pl show <name>` — show tracks in a playlist\n'
        '`!pl add <name> <url>` — add a track to an existing playlist\n'
        '`!pl remove <name> <number>` — remove a track by its number\n'
        '`!pl delete <name>` — delete a playlist entirely'
    )


@playlist_group.command(name='save')
async def playlist_save(ctx: commands.Context, *, name: str):
    state = get_state(ctx.guild.id)
    if not state['queue']:
        return await ctx.send('The queue is empty — nothing to save.')
    data = load_playlists()
    gid  = str(ctx.guild.id)
    data.setdefault(gid, {})[name] = [track_to_storable(t) for t in state['queue']]
    save_playlists(data)
    log.info('Playlist saved: "%s" (%d tracks) by %s', name, len(state['queue']), ctx.author)
    await ctx.send(f'Saved **{name}** with {len(state["queue"])} track(s).')


@playlist_group.command(name='load')
async def playlist_load(ctx: commands.Context, *, name: str):
    if not await ensure_voice(ctx):
        return
    data   = load_playlists()
    tracks = data.get(str(ctx.guild.id), {}).get(name)
    if not tracks:
        return await ctx.send(f'No playlist named **{name}**. Use `!pl list` to see all.')
    state = get_state(ctx.guild.id)
    state['queue'].extend(tracks)
    log.info('Playlist loaded: "%s" (%d tracks) by %s', name, len(tracks), ctx.author)
    await ctx.send(f'Loaded **{name}** — {len(tracks)} track(s) added to queue.')
    if not (state['voice_client'].is_playing() or state['voice_client'].is_paused()):
        await play_next(ctx.guild.id, ctx.channel)


@playlist_group.command(name='list')
async def playlist_list(ctx: commands.Context):
    data      = load_playlists()
    playlists = data.get(str(ctx.guild.id), {})
    if not playlists:
        return await ctx.send('No saved playlists yet.')
    lines = [f'`{name}` — {len(tracks)} track(s)' for name, tracks in playlists.items()]
    await ctx.send('**Saved playlists:**\n' + '\n'.join(lines))


@playlist_group.command(name='show')
async def playlist_show(ctx: commands.Context, *, name: str):
    data   = load_playlists()
    tracks = data.get(str(ctx.guild.id), {}).get(name)
    if tracks is None:
        return await ctx.send(f'No playlist named **{name}**.')
    if not tracks:
        return await ctx.send(f'**{name}** is empty.')
    lines = [
        f'`{i}.` **{t["title"]}**{duration_tag(t["duration"])}'
        for i, t in enumerate(tracks, 1)
    ]
    await ctx.send(f'**{name}** ({len(tracks)} tracks):\n' + '\n'.join(lines))


@playlist_group.command(name='add')
async def playlist_add(ctx: commands.Context, name: str, *, url: str):
    data = load_playlists()
    gid  = str(ctx.guild.id)
    if name not in data.get(gid, {}):
        return await ctx.send(
            f'No playlist named **{name}**. '
            f'Create one first with `!pl save {name}` after queuing some tracks.'
        )
    await ctx.send('Downloading track info...')
    try:
        loop  = asyncio.get_event_loop()
        track = await loop.run_in_executor(None, download_track, url)
    except Exception as e:
        log.error('Failed to add track to playlist "%s": %s', name, e, exc_info=True)
        return await ctx.send(f'Could not fetch track: `{e}`')
    data[gid][name].append(track_to_storable(track))
    save_playlists(data)
    log.info('Track added to playlist "%s": %s (by %s)', name, track['title'], ctx.author)
    await ctx.send(f'Added **{track["title"]}** to **{name}**.')


@playlist_group.command(name='remove')
async def playlist_remove(ctx: commands.Context, name: str, number: int):
    data   = load_playlists()
    gid    = str(ctx.guild.id)
    tracks = data.get(gid, {}).get(name)
    if tracks is None:
        return await ctx.send(f'No playlist named **{name}**.')
    if number < 1 or number > len(tracks):
        return await ctx.send(f'Number must be between 1 and {len(tracks)}.')
    removed = tracks.pop(number - 1)
    save_playlists(data)
    await ctx.send(f'Removed **{removed["title"]}** from **{name}**.')


@playlist_group.command(name='delete')
async def playlist_delete(ctx: commands.Context, *, name: str):
    data = load_playlists()
    gid  = str(ctx.guild.id)
    if name not in data.get(gid, {}):
        return await ctx.send(f'No playlist named **{name}**.')
    del data[gid][name]
    save_playlists(data)
    log.info('Playlist deleted: "%s" by %s', name, ctx.author)
    await ctx.send(f'Deleted playlist **{name}**.')


# ═══════════════════════════════════════════════════════════════════
#  Events
# ═══════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    log.info('Logged in as %s (ID: %s)', bot.user, bot.user.id)
    log.info('Download cache: %s', DOWNLOADS_DIR)
    log.info('Log file: %s', LOGS_DIR / 'music-bot.log')
    log.info('Bot is ready.')


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'Missing argument: `{error.param.name}`')
        return
    log.error(
        'Unhandled command error — command: %s | user: %s | guild: %s | error: %s',
        ctx.command, ctx.author, ctx.guild.id, error,
        exc_info=error,
    )


@bot.event
async def on_message(message):
    await bot.process_commands(message)


# --- Run ---
load_dotenv()
token = os.getenv('DISCORD_TOKEN')
if not token:
    raise ValueError('DISCORD_TOKEN not set in .env file')

bot.run(token, log_handler=None)
