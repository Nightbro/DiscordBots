import asyncio
import logging
from collections import deque
from pathlib import Path

import discord

from .downloader import download_track, FFMPEG_OPTIONS, duration_tag

log = logging.getLogger('music-bot.player')


def get_state(bot, guild_id: int) -> dict:
    if guild_id not in bot.guild_states:
        bot.guild_states[guild_id] = {'queue': deque(), 'voice_client': None}
    return bot.guild_states[guild_id]


async def play_next(bot, guild_id: int, channel):
    state = get_state(bot, guild_id)
    vc: discord.VoiceClient = state['voice_client']

    if not state['queue']:
        await channel.send('Queue finished. Use `!play` to add more songs.')
        return

    track = state['queue'].popleft()
    is_intro = track.get('_intro', False)

    if not is_intro and (not track.get('file') or not Path(track['file']).exists()):
        await channel.send(f'Downloading **{track["title"]}**...')
        try:
            loop = asyncio.get_event_loop()
            track = await loop.run_in_executor(None, download_track, track['webpage_url'])
        except Exception as e:
            log.error('Failed to download playlist track "%s": %s', track.get('title'), e, exc_info=True)
            await channel.send(f'Failed to download track: `{e}` — skipping.')
            await play_next(bot, guild_id, channel)
            return

    source = discord.FFmpegPCMAudio(track['file'], **FFMPEG_OPTIONS)

    def after(error):
        if error:
            log.error('Player error in guild %s: %s', guild_id, error, exc_info=error)
        asyncio.run_coroutine_threadsafe(play_next(bot, guild_id, channel), bot.loop)

    vc.play(source, after=after)
    if not is_intro:
        log.info('Now playing in guild %s: %s', guild_id, track['title'])
        await channel.send(f'Now playing: **{track["title"]}**{duration_tag(track["duration"])}')
