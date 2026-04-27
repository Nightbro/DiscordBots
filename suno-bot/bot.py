# ── SSL fix: must be FIRST before any other imports ──────────────────────────
import ssl
import certifi

def _patched_ssl_context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None):
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
import urllib.request
from collections import deque
from pathlib import Path

import discord
from discord.ext import commands
import yt_dlp
from dotenv import load_dotenv

# --- Paths ---
BASE_DIR      = Path(__file__).parent
DOWNLOADS_DIR = BASE_DIR / 'downloads'
PLAYLISTS_FILE = BASE_DIR / 'playlists.json'
DOWNLOADS_DIR.mkdir(exist_ok=True)

# --- Suno URL patterns ---
SUNO_RE = re.compile(
    r'(?:https?://)?(?:www\.)?(?:suno\.com|app\.suno\.ai)/(?:song|s)/([a-zA-Z0-9-]+)'
)
SUNO_UUID_RE = re.compile(
    r'/song/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
)

# --- yt-dlp options ---
# Info-only (no download) — used to read metadata and check cache key
YDL_INFO = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch',
}

# Download + convert to MP3
YDL_DOWNLOAD = {
    **YDL_INFO,
    'outtmpl': str(DOWNLOADS_DIR / '%(id)s.%(ext)s'),
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
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


def format_duration(seconds) -> str:
    if not seconds:
        return '?:??'
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f'{h}:{m:02}:{s:02}' if h else f'{m}:{s:02}'


# ── Download logic ────────────────────────────────────────────────────────────

def download_youtube(query: str) -> dict:
    """
    Fetch metadata, check local cache, download + convert to MP3 if needed.
    Returns a track dict with a guaranteed local 'file' path.
    """
    with yt_dlp.YoutubeDL(YDL_INFO) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info:
            info = info['entries'][0]

    video_id   = info['id']
    title      = info.get('title', 'Unknown')
    duration   = info.get('duration', 0)
    source_url = info.get('webpage_url', query)
    cached     = DOWNLOADS_DIR / f'{video_id}.mp3'

    if not cached.exists():
        with yt_dlp.YoutubeDL(YDL_DOWNLOAD) as ydl:
            ydl.extract_info(source_url, download=True)

    return {
        'file': str(cached),
        'title': title,
        'duration': duration,
        'webpage_url': source_url,
    }


def download_suno(url: str) -> dict:
    """
    Resolve the Suno song UUID (handles both /song/<uuid> and /s/<shortid>),
    download the MP3 from Suno's CDN if not cached, return a track dict.
    """
    title     = 'Unknown Suno Track'
    duration  = 0
    song_uuid = None

    # yt-dlp knows how to resolve Suno URLs and gives us the UUID in info['id']
    try:
        with yt_dlp.YoutubeDL(YDL_INFO) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                info = info['entries'][0]
        title    = info.get('title', title)
        duration = info.get('duration') or 0
        raw_id   = info.get('id', '')
        if re.fullmatch(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', raw_id
        ):
            song_uuid = raw_id
        else:
            m = SUNO_UUID_RE.search(info.get('webpage_url', ''))
            if m:
                song_uuid = m.group(1)
    except Exception:
        pass

    # Fallback: UUID might already be in the original URL
    if not song_uuid:
        m = SUNO_UUID_RE.search(url)
        if m:
            song_uuid = m.group(1)

    if not song_uuid:
        raise ValueError(
            f'Could not resolve Suno song UUID from: {url}\n'
            'Make sure the song is public and the URL is correct.'
        )

    cached = DOWNLOADS_DIR / f'{song_uuid}.mp3'

    if not cached.exists():
        cdn_url = f'https://cdn1.suno.ai/{song_uuid}.mp3'
        req = urllib.request.Request(cdn_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as resp:
            cached.write_bytes(resp.read())

    return {
        'file': str(cached),
        'title': title,
        'duration': duration,
        'webpage_url': url,
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
            await channel.send(f'Failed to download track: `{e}` — skipping.')
            await play_next(guild_id, channel)
            return

    source = discord.FFmpegPCMAudio(track['file'], **FFMPEG_OPTIONS)

    def after(error):
        if error:
            print(f'Player error: {error}')
        asyncio.run_coroutine_threadsafe(play_next(guild_id, channel), bot.loop)

    vc.play(source, after=after)
    dur = format_duration(track['duration'])
    await channel.send(f'Now playing: **{track["title"]}** `[{dur}]`')


# ── Playlist persistence ──────────────────────────────────────────────────────

def load_playlists() -> dict:
    if PLAYLISTS_FILE.exists():
        return json.loads(PLAYLISTS_FILE.read_text(encoding='utf-8'))
    return {}


def save_playlists(data: dict):
    PLAYLISTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def track_to_storable(track: dict) -> dict:
    """Strip the local file path before saving — paths may change across restarts."""
    return {k: v for k, v in track.items() if k != 'file'}


# ═══════════════════════════════════════════════════════════════════
#  Playback commands
# ═══════════════════════════════════════════════════════════════════

@bot.command(name='play', aliases=['p'])
async def play(ctx: commands.Context, *, query: str):
    """Play a YouTube URL/search or Suno song URL. Queues if something is playing."""
    if not await ensure_voice(ctx):
        return

    label = 'Suno track' if is_suno_url(query) else f'`{query}`'
    await ctx.send(f'Downloading {label}...')

    try:
        loop = asyncio.get_event_loop()
        track = await loop.run_in_executor(None, download_track, query)
    except Exception as e:
        return await ctx.send(f'Could not download: `{e}`')

    state = get_state(ctx.guild.id)
    state['queue'].append(track)
    dur = format_duration(track['duration'])

    if state['voice_client'].is_playing() or state['voice_client'].is_paused():
        await ctx.send(
            f'Added to queue: **{track["title"]}** `[{dur}]` '
            f'(#{len(state["queue"])})'
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
        f'`{i}.` **{t["title"]}** `[{format_duration(t["duration"])}]`'
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
        f'`{i}.` **{t["title"]}** `[{format_duration(t["duration"])}]`'
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
        return await ctx.send(f'Could not fetch track: `{e}`')
    data[gid][name].append(track_to_storable(track))
    save_playlists(data)
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
    await ctx.send(f'Deleted playlist **{name}**.')


# ═══════════════════════════════════════════════════════════════════
#  Events
# ═══════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print(f'Download cache: {DOWNLOADS_DIR}')
    print('Bot is ready.')


@bot.event
async def on_message(message):
    await bot.process_commands(message)


# --- Run ---
load_dotenv()
token = os.getenv('DISCORD_TOKEN')
if not token:
    raise ValueError('DISCORD_TOKEN not set in .env file')

bot.run(token)
