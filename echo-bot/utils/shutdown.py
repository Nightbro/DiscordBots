"""
Maintenance-shutdown helpers.

announce_maintenance() iterates every guild the bot is in and:
  - sends an info embed to the last known text channel (state.last_text_channel_id)
  - plays a short TTS announcement in the voice channel if the bot is connected

Lives in utils/ so it can be imported and tested independently of bot.py's asyncio.run() call.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

import discord
import edge_tts

from utils.config import DOWNLOADS_DIR
from utils.guild_state import GuildState
from utils.message import MessageWriter

if TYPE_CHECKING:
    from discord.ext import commands

log = logging.getLogger(__name__)

DEFAULT_MAINTENANCE_MSG = 'The bot is shutting down for maintenance.'


async def announce_maintenance(
    bot: commands.Bot,
    guild_states: dict[int, GuildState],
    text: str = DEFAULT_MAINTENANCE_MSG,
) -> None:
    """Announce a maintenance shutdown to every guild the bot is in.

    For each guild:
      - Sends an info embed to the last known text channel (if any)
      - Plays TTS in the voice channel (if connected), using the guild's tts_voice
    """
    for guild in bot.guilds:
        state = guild_states.get(guild.id)
        if state is None:
            continue

        # ── text announcement ────────────────────────────────────────────
        if state.last_text_channel_id:
            channel = guild.get_channel(state.last_text_channel_id)
            if channel is not None:
                try:
                    await channel.send(
                        embed=MessageWriter.info('🔧 Maintenance', text)
                    )
                except Exception as exc:
                    log.warning(
                        'Could not send maintenance message to guild %s: %s',
                        guild.id, exc,
                    )

        # ── voice announcement ───────────────────────────────────────────
        vc = state.voice_client
        if vc and vc.is_connected():
            try:
                await _play_tts(vc, text, state.tts_voice)
            except Exception as exc:
                log.warning(
                    'Maintenance TTS failed for guild %s: %s',
                    guild.id, exc,
                )


async def _play_tts(vc: discord.VoiceClient, text: str, voice: str) -> None:
    """Generate edge-tts audio and play it through the voice client, waiting for it to finish."""
    tmp = DOWNLOADS_DIR / f'maintenance_{uuid.uuid4().hex}.mp3'
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(tmp))

        loop = asyncio.get_running_loop()
        done = asyncio.Event()

        def _after(_err: Exception | None) -> None:
            loop.call_soon_threadsafe(done.set)

        if vc.is_playing() or vc.is_paused():
            vc.stop()

        source = discord.FFmpegPCMAudio(str(tmp), options='-vn')
        vc.play(source, after=_after)
        await asyncio.wait_for(done.wait(), timeout=15.0)
    finally:
        tmp.unlink(missing_ok=True)
