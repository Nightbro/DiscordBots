"""
Notification dispatcher.

Routes bot responses through three independent channels controlled by per-guild settings:
  - write (default on)  — sends a Discord embed in the channel
  - say   (default off) — speaks the title via TTS in voice (if bot is connected)

When write is off the bot instead reacts to the invoking message:
  ✅ success  ❌ error  ❓ info / problem
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import edge_tts
import discord

from utils.config import DOWNLOADS_DIR
from utils.config import TTS_DEFAULT_VOICE
from utils.guild_config import (
    get_notify_say,
    get_notify_write,
    get_tts_rate,
    get_tts_voice,
    get_voice_language,
    has_override,
)
from utils.guild_state import Track
from utils.message import MessageWriter
from utils.voice import VoiceStreamer

log = logging.getLogger(__name__)

# Cache of locale-prefix → first matching edge-tts ShortName (populated on first use)
_voice_locale_cache: dict[str, str] = {}


async def resolve_tts_voice(guild_id: int) -> str:
    """
    Return the effective TTS voice for the guild.

    Priority:
      1. Explicit tts_voice override in guild settings
      2. voice_language locale code → auto-select the first matching voice
      3. TTS_DEFAULT_VOICE from config
    """
    if has_override(guild_id, 'tts_voice'):
        return get_tts_voice(guild_id)

    lang = get_voice_language(guild_id)
    if lang:
        if lang in _voice_locale_cache:
            return _voice_locale_cache[lang]
        try:
            voices = await edge_tts.list_voices()
            matches = [v for v in voices if v['Locale'].lower().startswith(lang.lower())]
            if matches:
                voice = matches[0]['ShortName']
                _voice_locale_cache[lang] = voice
                return voice
        except Exception as exc:
            log.warning('Could not resolve voice for language %r: %s', lang, exc)

    return TTS_DEFAULT_VOICE


_REACT: dict[str, str] = {
    'success': '✅',
    'error': '❌',
    'info': '❓',
}


class Notifier:
    """
    Stateless per-request helper. Create one per command invocation.

    Action responses (skip, pause, add sound, …) → success / error / info
    Loading states (resolving, synthesising, …)   → loading  (always written)
    Custom embeds (track_card, queue page, …)     → send
    """

    def __init__(self, bot: Any, guild_id: int) -> None:
        self._bot = bot
        self._gid = guild_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def loading(self, ctx, title: str) -> discord.Message | None:
        """
        Show an in-progress indicator.

        Write mode: sends an info embed and returns the message for later editing.
        React mode: reacts ⏳ and returns None.
        """
        if get_notify_write(self._gid):
            return await ctx.send(embed=MessageWriter.info(title))
        try:
            await ctx.message.add_reaction('⏳')
        except Exception:
            pass
        return None

    async def success(
        self,
        ctx,
        title: str,
        description: str = '',
        *,
        loading: discord.Message | None = None,
    ) -> None:
        embed = MessageWriter.success(title, description)
        await self._dispatch(ctx, embed, 'success', title, loading)

    async def error(
        self,
        ctx,
        title: str,
        description: str = '',
        *,
        loading: discord.Message | None = None,
    ) -> None:
        embed = MessageWriter.error(title, description)
        await self._dispatch(ctx, embed, 'error', title, loading)

    async def info(
        self,
        ctx,
        title: str,
        description: str = '',
        *,
        loading: discord.Message | None = None,
    ) -> None:
        embed = MessageWriter.info(title, description)
        await self._dispatch(ctx, embed, 'info', title, loading)

    async def send(
        self,
        ctx,
        embed: discord.Embed,
        *,
        tts_text: str = '',
        level: str = 'success',
        loading: discord.Message | None = None,
    ) -> None:
        """Send a custom embed (e.g. track_card). Falls back to react when write is off."""
        await self._dispatch(ctx, embed, level, tts_text, loading)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _dispatch(
        self,
        ctx,
        embed: discord.Embed,
        level: str,
        speak_text: str,
        loading: discord.Message | None,
    ) -> None:
        if get_notify_write(self._gid):
            if loading is not None:
                await loading.edit(embed=embed)
            else:
                await ctx.send(embed=embed)
        else:
            await self._react(ctx, level)

        if get_notify_say(self._gid) and speak_text:
            await self._speak(speak_text)

    async def _react(self, ctx, level: str) -> None:
        emoji = _REACT.get(level, '❓')
        try:
            await ctx.message.remove_reaction('⏳', ctx.guild.me)
        except Exception:
            pass
        try:
            await ctx.message.add_reaction(emoji)
        except Exception:
            pass

    async def _speak(self, text: str) -> None:
        state = self._bot.get_guild_state(self._gid)
        if not state.voice_client or not state.voice_client.is_connected():
            return
        try:
            voice = await resolve_tts_voice(self._gid)
            rate = get_tts_rate(self._gid)
            tmp = DOWNLOADS_DIR / f'notify_{uuid.uuid4().hex}.mp3'
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(str(tmp))
            track = Track(
                title=f'Notify: {text[:40]}',
                url=str(tmp),
                file_path=tmp,
                cleanup_path=tmp,
            )
            await VoiceStreamer(self._bot, self._gid).interrupt(track)
        except Exception as exc:
            log.warning('Notifier TTS speak failed for guild %s: %s', self._gid, exc)
