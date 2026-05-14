import asyncio
import logging
from collections import deque
from pathlib import Path

import discord

from .downloader import download_track, FFMPEG_OPTIONS, duration_tag

log = logging.getLogger('music-bot.player')


def get_state(bot, guild_id: int) -> dict:
    if guild_id not in bot.guild_states:
        bot.guild_states[guild_id] = {
            'queue': deque(),
            'voice_client': None,
            'current_track': None,
            'last_channel': None,
        }
    return bot.guild_states[guild_id]


async def play_next(bot, guild_id: int, channel):
    state = get_state(bot, guild_id)
    if channel is not None:
        state['last_channel'] = channel
    vc: discord.VoiceClient = state['voice_client']

    if not state['queue']:
        state['current_track'] = None
        if channel:
            await channel.send('Queue finished. Use `!play` to add more songs.')
        return

    track = state['queue'].popleft()
    is_intro = track.get('_intro', False)

    if not is_intro and (not track.get('file') or not Path(track['file']).exists()):
        if channel:
            await channel.send(f'Downloading **{track["title"]}**...')
        try:
            loop = asyncio.get_event_loop()
            track = await loop.run_in_executor(None, download_track, track['webpage_url'])
        except Exception as e:
            log.error('Failed to download playlist track "%s": %s', track.get('title'), e, exc_info=True)
            if channel:
                await channel.send(f'Failed to download track: `{e}` — skipping.')
            await play_next(bot, guild_id, channel)
            return

    state['current_track'] = track
    source = discord.FFmpegPCMAudio(track['file'], **FFMPEG_OPTIONS)

    def after(error):
        state['current_track'] = None
        if error:
            log.error('Player error in guild %s: %s', guild_id, error, exc_info=error)
        if state.get('_interrupted'):
            return
        asyncio.run_coroutine_threadsafe(play_next(bot, guild_id, channel), bot.loop)

    vc.play(source, after=after)
    if not is_intro:
        log.info('Now playing in guild %s: %s', guild_id, track['title'])
        if channel:
            await channel.send(f'Now playing: **{track["title"]}**{duration_tag(track["duration"])}')


async def play_with_interrupt(bot, guild_id: int, audio_path: str, channel=None):
    """Play a one-shot sound, pausing any current music and resuming it after."""
    state = get_state(bot, guild_id)
    vc: discord.VoiceClient = state['voice_client']
    resume_channel = channel or state.get('last_channel')

    was_active = vc.is_playing() or vc.is_paused()
    current = state.get('current_track')

    if was_active:
        state['_interrupted'] = True
        # Re-queue current track so it resumes after the sound (skip intros)
        if current and not current.get('_intro'):
            state['queue'].appendleft(current)
        state['current_track'] = None
        vc.stop()

    def after_interrupt(error):
        if error:
            log.error('Interrupt playback error in guild %s: %s', guild_id, error)
        state.pop('_interrupted', None)
        if was_active and resume_channel:
            asyncio.run_coroutine_threadsafe(
                play_next(bot, guild_id, resume_channel), bot.loop
            )

    vc.play(discord.FFmpegPCMAudio(str(audio_path), **FFMPEG_OPTIONS), after=after_interrupt)
