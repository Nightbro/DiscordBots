import asyncio
import logging
import shutil
from pathlib import Path

import discord
from discord.ext import commands

from utils.config import SOUNDBOARD_DIR
from utils.downloader import download_track, FFMPEG_OPTIONS
from utils.player import get_state
from utils.soundboard_config import get_sounds, get_sound, add_sound, remove_sound

log = logging.getLogger('music-bot.soundboard')

_YES = '✅'
_NO  = '❌'


class SoundboardCog(commands.Cog, name='Soundboard'):
    def __init__(self, bot):
        self.bot = bot

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _ask_to_join(self, ctx: commands.Context) -> bool:
        msg = await ctx.send("I'm not in a voice channel. Do you want me to join?")
        for emoji in (_YES, _NO):
            await msg.add_reaction(emoji)

        def check(reaction, user):
            return (
                user.id == ctx.author.id
                and reaction.message.id == msg.id
                and str(reaction.emoji) in (_YES, _NO)
            )

        reaction = None
        try:
            reaction, _ = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
        except asyncio.TimeoutError:
            pass

        if reaction is not None:
            try:
                await msg.remove_reaction(reaction.emoji, ctx.author)
            except discord.Forbidden:
                pass

        for emoji in (_YES, _NO):
            try:
                await msg.remove_reaction(emoji, ctx.me)
            except discord.HTTPException:
                pass

        if reaction is None:
            await msg.edit(content="Confirmation timed out.")
            return False

        if str(reaction.emoji) == _YES:
            await msg.edit(content="I'm not in a voice channel — joining now!")
            return True

        await msg.edit(content="I'm not in a voice channel — got it, staying out.")
        return False

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.group(name='soundboard', aliases=['sb'], invoke_without_command=True)
    async def sb_group(self, ctx: commands.Context):
        await ctx.send(
            '**Soundboard commands:**\n'
            '`!sb add <name> <emoji> [url/search]` — add a sound (attach MP3 or provide URL)\n'
            '`!sb remove <name>` — remove a sound\n'
            '`!sb trigger <name>` — play a sound\n'
            '`!sb list` — list all sounds for this server'
        )

    @sb_group.command(name='add')
    async def sb_add(self, ctx: commands.Context, name: str, emoji: str, *, query: str = None):
        dest = SOUNDBOARD_DIR / f'{ctx.guild.id}_{name}.mp3'

        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if not attachment.filename.lower().endswith('.mp3'):
                return await ctx.send('Only MP3 attachments are supported.')
            await ctx.send('Saving attachment...')
            dest.write_bytes(await attachment.read())
            source_label = attachment.filename
            log.info('Soundboard add from attachment — guild %s name %s', ctx.guild.id, name)
        elif query:
            await ctx.send(f'Downloading **{name}**...')
            try:
                loop  = asyncio.get_event_loop()
                track = await loop.run_in_executor(None, download_track, query)
            except Exception as e:
                log.error('Soundboard download failed — guild %s name %s: %s',
                          ctx.guild.id, name, e, exc_info=True)
                return await ctx.send(f'Could not download: `{e}`')
            shutil.copy(track['file'], dest)
            source_label = query
            log.info('Soundboard add from URL — guild %s name %s: %s',
                     ctx.guild.id, name, source_label)
        else:
            return await ctx.send('Provide a URL/search term or attach an MP3 file.')

        add_sound(ctx.guild.id, name, emoji, str(dest), source_label)
        await ctx.send(f'Sound **{name}** {emoji} added.')

    @sb_group.command(name='remove')
    async def sb_remove(self, ctx: commands.Context, *, name: str):
        entry = remove_sound(ctx.guild.id, name)
        if not entry:
            return await ctx.send(f'No sound named **{name}**.')
        Path(entry['file']).unlink(missing_ok=True)
        log.info('Soundboard remove — guild %s name %s', ctx.guild.id, name)
        await ctx.send(f'Sound **{name}** removed.')

    @sb_group.command(name='trigger')
    async def sb_trigger(self, ctx: commands.Context, *, name: str):
        entry = get_sound(ctx.guild.id, name)
        if not entry:
            return await ctx.send(f'No sound named **{name}**.')

        if not ctx.author.voice:
            await ctx.send("I will not listen to someone who doesn't even have the courage to show up.")
            return

        state = get_state(self.bot, ctx.guild.id)
        vc: discord.VoiceClient = state['voice_client']

        if vc is not None and vc.is_connected():
            if ctx.author.voice.channel != vc.channel:
                await ctx.send("Sorry, I cannot hear you — I am kinda busy.")
                return
        else:
            if not await self._ask_to_join(ctx):
                return
            state['voice_client'] = await ctx.author.voice.channel.connect()
            vc = state['voice_client']

        if vc.is_playing() or vc.is_paused():
            return await ctx.send('Cannot play sound while audio is already playing.')

        sound_file = Path(entry['file'])
        if not sound_file.exists():
            return await ctx.send(f'Sound file for **{name}** is missing.')

        log.info('Soundboard trigger — guild %s name %s (by %s)', ctx.guild.id, name, ctx.author)
        vc.play(discord.FFmpegPCMAudio(str(sound_file), **FFMPEG_OPTIONS))
        await ctx.send(f'Playing **{name}** {entry["emoji"]}.')

    @sb_group.command(name='list')
    async def sb_list(self, ctx: commands.Context):
        sounds = get_sounds(ctx.guild.id)
        if not sounds:
            return await ctx.send('No sounds configured for this server yet.')
        lines = [
            f'{entry["emoji"]} **{name}** — `{entry["source"]}`'
            for name, entry in sounds.items()
        ]
        await ctx.send('**Soundboard:**\n' + '\n'.join(lines))


async def setup(bot):
    await bot.add_cog(SoundboardCog(bot))
