from __future__ import annotations

import logging
import re
import uuid

import edge_tts
import discord
from discord.ext import commands

from utils.config import DOWNLOADS_DIR
from utils.guild_config import get_tts_rate, get_tts_voice, set_tts_rate, set_tts_voice
from utils.guild_state import Track
from utils.i18n import t
from utils.message import MessageWriter
from utils.notifier import Notifier
from utils.voice import VoiceStreamer

log = logging.getLogger(__name__)

_VOICES_PAGE = 20
_RATE_RE = re.compile(r'^[+-]\d+%$')


class TTSCog(commands.Cog, name='TTS'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _notifier(self, ctx) -> Notifier:
        return Notifier(self.bot, ctx.guild.id)

    async def _ensure_voice(self, ctx) -> VoiceStreamer | None:
        gid = ctx.guild.id
        if ctx.author.voice is None:
            await self._notifier(ctx).error(ctx, t('common.error_no_voice', gid))
            return None
        streamer = VoiceStreamer(self.bot, gid)
        await streamer.join(ctx.author.voice.channel)
        return streamer

    # -----------------------------------------------------------------------
    # !say
    # -----------------------------------------------------------------------

    @commands.hybrid_command(name='say')
    async def say(self, ctx: commands.Context, *, text: str) -> None:
        """Speak text in your voice channel."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        streamer = await self._ensure_voice(ctx)
        if streamer is None:
            return

        voice = get_tts_voice(gid)
        rate = get_tts_rate(gid)

        tmp_path = DOWNLOADS_DIR / f'tts_{uuid.uuid4().hex}.mp3'
        loading = await notifier.loading(ctx, t('tts.synthesizing', gid))
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(str(tmp_path))
        except Exception as exc:
            log.error('TTS synthesis failed for guild %s: %s', gid, exc)
            await notifier.error(ctx, t('tts.error_synthesis', gid), str(exc), loading=loading)
            return

        track = Track(
            title=f'TTS: {text[:50]}',
            url=str(tmp_path),
            file_path=tmp_path,
            cleanup_path=tmp_path,
        )
        await streamer.interrupt(track)
        await notifier.success(ctx, t('tts.speaking', gid), loading=loading)

    # -----------------------------------------------------------------------
    # !tts group
    # -----------------------------------------------------------------------

    @commands.hybrid_group(name='tts', invoke_without_command=True)
    async def tts(self, ctx: commands.Context) -> None:
        """TTS settings and controls."""
        gid = ctx.guild.id
        await ctx.send(embed=MessageWriter.info('TTS', t('tts.hint', gid)))

    @tts.command(name='voice')
    async def tts_voice(self, ctx: commands.Context, *, name: str) -> None:
        """Set the TTS voice for this server (use !tts voices to see options)."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        loading = await notifier.loading(ctx, t('tts.validating', gid))
        try:
            voices = await edge_tts.list_voices()
            valid = {v['ShortName'] for v in voices}
        except Exception as exc:
            await notifier.error(ctx, t('tts.error_voices', gid), str(exc), loading=loading)
            return

        if name not in valid:
            await notifier.error(
                ctx,
                t('tts.voice_not_found', gid, name=name),
                t('tts.voice_not_found_hint', gid),
                loading=loading,
            )
            return

        set_tts_voice(gid, name)
        await notifier.success(ctx, t('tts.voice_set', gid, name=name), loading=loading)

    @tts.command(name='voices')
    async def tts_voices(self, ctx: commands.Context, locale: str = '') -> None:
        """List available TTS voices. Filter by locale prefix, e.g. `en` or `sr`."""
        gid = ctx.guild.id
        loading = await ctx.send(embed=MessageWriter.info(t('tts.loading_voices', gid)))
        try:
            voices = await edge_tts.list_voices()
        except Exception as exc:
            await loading.edit(embed=MessageWriter.error(t('tts.error_voices', gid), str(exc)))
            return

        if locale:
            voices = [v for v in voices if v['Locale'].lower().startswith(locale.lower())]

        if not voices:
            await loading.edit(embed=MessageWriter.error(
                t('tts.no_voices_found', gid, locale=locale),
            ))
            return

        lines = [f'`{v["ShortName"]}` — {v["FriendlyName"]}' for v in voices[:_VOICES_PAGE]]
        if len(voices) > _VOICES_PAGE:
            lines.append(t('tts.voices_more', gid, count=len(voices) - _VOICES_PAGE))
        await loading.edit(embed=MessageWriter.info(
            t('tts.voices_title', gid),
            '\n'.join(lines),
        ))

    @tts.command(name='rate')
    async def tts_rate(self, ctx: commands.Context, rate: str) -> None:
        """Set the TTS speech rate, e.g. `+10%`, `-20%`, `+0%`."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        if not _RATE_RE.match(rate):
            await notifier.error(
                ctx,
                t('tts.rate_invalid', gid),
                t('tts.rate_invalid_hint', gid),
            )
            return
        set_tts_rate(gid, rate)
        await notifier.success(ctx, t('tts.rate_set', gid, rate=rate))

    @tts.command(name='stop')
    async def tts_stop(self, ctx: commands.Context) -> None:
        """Stop whatever TTS is currently speaking."""
        gid = ctx.guild.id
        streamer = VoiceStreamer(self.bot, gid)
        await streamer.skip()
        await self._notifier(ctx).success(ctx, t('tts.stopped', gid))

    @tts.command(name='show')
    async def tts_show(self, ctx: commands.Context) -> None:
        """Show current TTS voice and rate for this server."""
        gid = ctx.guild.id
        voice = get_tts_voice(gid)
        rate = get_tts_rate(gid)
        await ctx.send(embed=MessageWriter.info(
            t('tts.show_title', gid),
            t('tts.show_desc', gid, voice=voice, rate=rate),
        ))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TTSCog(bot))
