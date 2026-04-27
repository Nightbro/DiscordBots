# ── SSL fix: must be FIRST before any other imports ──────────────────────────
# Miniconda on Windows has corrupted certs in the Windows cert store.
# This replaces ssl.create_default_context() so it uses certifi instead.
import ssl
import certifi

def _patched_ssl_context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(cafile or certifi.where(), capath, cadata)
    return ctx

ssl.create_default_context = _patched_ssl_context
# ─────────────────────────────────────────────────────────────────────────────

import discord
from discord.ext import commands
import yt_dlp
import asyncio
from collections import deque

# --- Configuration ---
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',  # no video, audio only
}

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch',  # allows searching by name, not just URL
}

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Per-guild state: {guild_id: {'queue': deque, 'voice_client': VoiceClient}}
guilds = {}


def get_guild_state(guild_id):
    if guild_id not in guilds:
        guilds[guild_id] = {'queue': deque(), 'voice_client': None}
    return guilds[guild_id]


def fetch_audio_info(query: str) -> dict:
    """Fetch audio URL and metadata from YouTube (runs in executor to avoid blocking)."""
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info:
            info = info['entries'][0]  # take first search result
        return {
            'url': info['url'],
            'title': info.get('title', 'Unknown'),
            'duration': info.get('duration', 0),
            'webpage_url': info.get('webpage_url', ''),
        }


def format_duration(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours}:{minutes:02}:{secs:02}'
    return f'{minutes}:{secs:02}'


async def play_next(guild_id: int, text_channel: discord.TextChannel):
    """Play the next song in the queue."""
    state = get_guild_state(guild_id)
    vc: discord.VoiceClient = state['voice_client']

    if not state['queue']:
        await text_channel.send('Queue is empty. Use `!play` to add songs.')
        return

    track = state['queue'].popleft()
    source = discord.FFmpegPCMAudio(track['url'], **FFMPEG_OPTIONS)

    def after_playing(error):
        if error:
            print(f'Player error: {error}')
        asyncio.run_coroutine_threadsafe(play_next(guild_id, text_channel), bot.loop)

    vc.play(source, after=after_playing)
    duration = format_duration(track['duration'])
    await text_channel.send(f'Now playing: **{track["title"]}** `[{duration}]`')


# --- Commands ---

@bot.command(name='play', aliases=['p'])
async def play(ctx: commands.Context, *, query: str):
    """Play a YouTube video by URL or search term. Adds to queue if something is already playing."""
    voice_channel = ctx.author.voice.channel if ctx.author.voice else None
    if not voice_channel:
        return await ctx.send('You need to be in a voice channel first.')

    state = get_guild_state(ctx.guild.id)

    # Join or move to the user's voice channel
    if state['voice_client'] is None or not state['voice_client'].is_connected():
        state['voice_client'] = await voice_channel.connect()
    elif state['voice_client'].channel != voice_channel:
        await state['voice_client'].move_to(voice_channel)

    await ctx.send(f'Searching for: `{query}`...')

    try:
        loop = asyncio.get_event_loop()
        track = await loop.run_in_executor(None, fetch_audio_info, query)
    except Exception as e:
        return await ctx.send(f'Could not fetch audio: `{e}`')

    state['queue'].append(track)
    duration = format_duration(track['duration'])

    if state['voice_client'].is_playing() or state['voice_client'].is_paused():
        await ctx.send(f'Added to queue: **{track["title"]}** `[{duration}]` (position {len(state["queue"])})')
    else:
        await play_next(ctx.guild.id, ctx.channel)


@bot.command(name='skip', aliases=['s'])
async def skip(ctx: commands.Context):
    """Skip the current song."""
    state = get_guild_state(ctx.guild.id)
    vc = state['voice_client']

    if vc and vc.is_playing():
        vc.stop()  # triggers after_playing -> play_next
        await ctx.send('Skipped.')
    else:
        await ctx.send('Nothing is playing.')


@bot.command(name='pause')
async def pause(ctx: commands.Context):
    """Pause the current song."""
    state = get_guild_state(ctx.guild.id)
    vc = state['voice_client']

    if vc and vc.is_playing():
        vc.pause()
        await ctx.send('Paused.')
    else:
        await ctx.send('Nothing is playing.')


@bot.command(name='resume', aliases=['r'])
async def resume(ctx: commands.Context):
    """Resume a paused song."""
    state = get_guild_state(ctx.guild.id)
    vc = state['voice_client']

    if vc and vc.is_paused():
        vc.resume()
        await ctx.send('Resumed.')
    else:
        await ctx.send('Nothing is paused.')


@bot.command(name='stop')
async def stop(ctx: commands.Context):
    """Stop playback and clear the queue."""
    state = get_guild_state(ctx.guild.id)
    vc = state['voice_client']

    state['queue'].clear()
    if vc:
        vc.stop()
        await vc.disconnect()
        state['voice_client'] = None

    await ctx.send('Stopped and disconnected.')


@bot.command(name='queue', aliases=['q'])
async def queue(ctx: commands.Context):
    """Show the current queue."""
    state = get_guild_state(ctx.guild.id)

    if not state['queue']:
        return await ctx.send('The queue is empty.')

    lines = []
    for i, track in enumerate(state['queue'], start=1):
        duration = format_duration(track['duration'])
        lines.append(f'`{i}.` **{track["title"]}** `[{duration}]`')

    await ctx.send('**Queue:**\n' + '\n'.join(lines))


@bot.command(name='clear')
async def clear(ctx: commands.Context):
    """Clear the queue without stopping current song."""
    state = get_guild_state(ctx.guild.id)
    state['queue'].clear()
    await ctx.send('Queue cleared.')


@bot.command(name='leave', aliases=['dc'])
async def leave(ctx: commands.Context):
    """Disconnect the bot from voice."""
    state = get_guild_state(ctx.guild.id)
    vc = state['voice_client']

    if vc and vc.is_connected():
        state['queue'].clear()
        await vc.disconnect()
        state['voice_client'] = None
        await ctx.send('Disconnected.')
    else:
        await ctx.send('Not connected to a voice channel.')


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('Bot is ready.')


@bot.event
async def on_message(message):
    await bot.process_commands(message)


# --- Run ---
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

if not token:
    raise ValueError('DISCORD_TOKEN not set in .env file')

bot.run(token)
