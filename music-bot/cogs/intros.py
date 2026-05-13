import asyncio
import logging
import shutil
from pathlib import Path

import discord
from discord.ext import commands

from utils.config import INTRO_SOUNDS_DIR, _INTRO_FILE, _INTRO_ON_BOT_JOIN, _INTRO_ON_USER_JOIN
from utils.downloader import download_track, FFMPEG_OPTIONS
from utils.player import get_state
from utils.intro_config import load_intro_config, save_intro_config, get_intro_file

log = logging.getLogger('music-bot.intros')


class IntrosCog(commands.Cog, name='Intros'):
    def __init__(self, bot):
        self.bot = bot

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.group(name='intro', aliases=['in'], invoke_without_command=True)
    async def intro_group(self, ctx: commands.Context):
        await ctx.send(
            '**Intro commands:**\n'
            '`!intro set bot <url>` — set bot-join intro (or attach an MP3)\n'
            '`!intro set user <url>` — set user-join intro (or attach an MP3)\n'
            '`!intro clear bot` — remove bot-join intro\n'
            '`!intro clear user` — remove user-join intro\n'
            '`!intro show` — show current intro config'
        )

    @intro_group.command(name='set')
    async def intro_set(self, ctx: commands.Context, trigger: str, *, query: str = None):
        if trigger not in ('bot', 'user'):
            return await ctx.send('Trigger must be `bot` or `user`.')

        dest = INTRO_SOUNDS_DIR / f'{ctx.guild.id}_{trigger}.mp3'

        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if not attachment.filename.lower().endswith('.mp3'):
                return await ctx.send('Only MP3 attachments are supported.')
            await ctx.send('Saving attachment...')
            dest.write_bytes(await attachment.read())
            source_label = attachment.filename
            log.info('Intro set from attachment — guild %s trigger %s: %s', ctx.guild.id, trigger, source_label)
        elif query:
            await ctx.send(f'Downloading **{trigger}**-join intro...')
            try:
                loop  = asyncio.get_event_loop()
                track = await loop.run_in_executor(None, download_track, query)
            except Exception as e:
                log.error('Intro download failed for guild %s: %s', ctx.guild.id, e, exc_info=True)
                return await ctx.send(f'Could not download: `{e}`')
            shutil.copy(track['file'], dest)
            source_label = query
            log.info('Intro set from URL — guild %s trigger %s: %s', ctx.guild.id, trigger, source_label)
        else:
            return await ctx.send('Provide a URL/search term or attach an MP3 file.')

        config = load_intro_config()
        config.setdefault(str(ctx.guild.id), {})[trigger] = {
            'file': str(dest),
            'source': source_label,
        }
        save_intro_config(config)
        await ctx.send(f'**{trigger.capitalize()}-join** intro set to `{dest.name}`.')

    @intro_group.command(name='clear')
    async def intro_clear(self, ctx: commands.Context, trigger: str):
        if trigger not in ('bot', 'user'):
            return await ctx.send('Trigger must be `bot` or `user`.')

        config = load_intro_config()
        gid    = str(ctx.guild.id)
        entry  = config.get(gid, {}).pop(trigger, None)
        if not entry:
            return await ctx.send(f'No **{trigger}**-join intro is configured.')

        Path(entry['file']).unlink(missing_ok=True)
        save_intro_config(config)
        log.info('Intro cleared — guild %s trigger %s', ctx.guild.id, trigger)
        await ctx.send(f'**{trigger.capitalize()}-join** intro removed.')

    @intro_group.command(name='show')
    async def intro_show(self, ctx: commands.Context):
        config    = load_intro_config()
        guild_cfg = config.get(str(ctx.guild.id), {})

        lines = []
        for trigger, label in (('bot', 'Bot join'), ('user', 'User join')):
            entry = guild_cfg.get(trigger)
            if entry:
                p       = Path(entry['file'])
                missing = ' *(file missing!)*' if not p.exists() else ''
                lines.append(f'**{label}:** `{p.name}`  —  source: `{entry["source"]}`{missing}')
            else:
                fallback = f'fallback: `{_INTRO_FILE.name}`' if _INTRO_FILE.exists() else 'not set'
                lines.append(f'**{label}:** *(not configured — {fallback})*')

        active = []
        if _INTRO_ON_BOT_JOIN:
            active.append('bot join')
        if _INTRO_ON_USER_JOIN:
            active.append('user join')
        active_str = ', '.join(active) if active else 'none (both disabled in .env)'

        await ctx.send(
            '**Intro config:**\n' + '\n'.join(lines) +
            f'\n*Global triggers enabled: {active_str}*'
        )

    # ── Listener ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot or not _INTRO_ON_USER_JOIN:
            return
        if after.channel is None or before.channel == after.channel:
            return
        state = get_state(self.bot, member.guild.id)
        vc: discord.VoiceClient = state['voice_client']
        if vc is None or not vc.is_connected() or vc.channel != after.channel:
            return
        if vc.is_playing() or vc.is_paused():
            return
        intro = get_intro_file(member.guild.id, 'user')
        if not intro:
            return
        log.info('Playing user-join intro for %s in guild %s', member, member.guild.id)
        vc.play(discord.FFmpegPCMAudio(str(intro), **FFMPEG_OPTIONS))


async def setup(bot):
    await bot.add_cog(IntrosCog(bot))
