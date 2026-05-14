import asyncio
import logging
import shutil
from pathlib import Path

import discord
from discord.ext import commands

from utils.config import SOUNDBOARD_DIR, AUDIO_EXTS
from utils.downloader import download_track, FFMPEG_OPTIONS
from utils.player import get_state, play_with_interrupt
from utils.soundboard_config import get_sounds, get_sound, add_sound, remove_sound

log = logging.getLogger('music-bot.soundboard')

_YES = '✅'
_NO  = '❌'


_PANEL_TIMEOUT = 300  # seconds of inactivity before panel is deleted


class SoundboardCog(commands.Cog, name='Soundboard'):
    def __init__(self, bot):
        self.bot = bot
        # guild_id -> (discord.Message, {emoji_str: sound_name})
        self._panels: dict[int, tuple] = {}
        # guild_id -> inactivity asyncio.Task
        self._panel_tasks: dict[int, asyncio.Task] = {}

    # ── Panel timeout ─────────────────────────────────────────────────────────

    async def _panel_timeout(self, guild_id: int):
        await asyncio.sleep(_PANEL_TIMEOUT)
        panel = self._panels.pop(guild_id, None)
        self._panel_tasks.pop(guild_id, None)
        if panel:
            panel_msg, _ = panel
            try:
                await panel_msg.clear_reactions()
            except discord.HTTPException:
                pass
            try:
                await panel_msg.edit(
                    content='*The soundboard has disappeared — use `!sb` or `!soundboard` to bring it back.*'
                )
            except discord.HTTPException:
                pass

    def _reset_panel_timer(self, guild_id: int):
        existing = self._panel_tasks.pop(guild_id, None)
        if existing:
            existing.cancel()
        self._panel_tasks[guild_id] = asyncio.get_event_loop().create_task(
            self._panel_timeout(guild_id)
        )

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

    async def _send_panel(self, ctx: commands.Context):
        """Post the interactive soundboard panel and register it for reactions."""
        sounds = get_sounds(ctx.guild.id)
        if not sounds:
            return await ctx.send('No sounds configured for this server yet.')

        lines = [
            f'{entry["emoji"]} **{name}** — `{entry["source"]}`'
            for name, entry in sounds.items()
        ]
        msg = await ctx.send('**Soundboard** — click a reaction to play:\n' + '\n'.join(lines))

        emoji_map: dict[str, str] = {}
        for name, entry in sounds.items():
            await msg.add_reaction(entry['emoji'])
            emoji_map[entry['emoji']] = name

        self._panels[ctx.guild.id] = (msg, emoji_map)
        self._reset_panel_timer(ctx.guild.id)

    async def _play_from_reaction(
        self,
        guild: discord.Guild,
        channel,
        member: discord.Member,
        sound_name: str,
    ):
        """Trigger a sound from a reaction click — auto-joins, no interactive prompt."""
        entry = get_sound(guild.id, sound_name)
        if not entry:
            return

        if not member.voice:
            await channel.send(
                f"{member.mention} I will not listen to someone who doesn't even have the courage to show up."
            )
            return

        state = get_state(self.bot, guild.id)
        vc: discord.VoiceClient = state['voice_client']

        if vc is not None and vc.is_connected():
            if member.voice.channel != vc.channel:
                await channel.send(f"{member.mention} Sorry, I cannot hear you — I am kinda busy.")
                return
        else:
            try:
                state['voice_client'] = await member.voice.channel.connect()
                vc = state['voice_client']
            except Exception as e:
                log.error('Failed to join voice from reaction — guild %s: %s', guild.id, e)
                return

        sound_file = Path(entry['file'])
        if not sound_file.exists():
            await channel.send(f'Sound file for **{sound_name}** is missing.')
            return

        log.info('Soundboard reaction — guild %s name %s by %s', guild.id, sound_name, member)
        await play_with_interrupt(self.bot, guild.id, str(sound_file), channel)
        await channel.send(f'{member.mention} Playing **{sound_name}** {entry["emoji"]}.')

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.group(name='soundboard', aliases=['sb'], invoke_without_command=True)
    async def sb_group(self, ctx: commands.Context):
        await self._send_panel(ctx)

    @sb_group.command(name='list')
    async def sb_list(self, ctx: commands.Context):
        await self._send_panel(ctx)

    @sb_group.command(name='add')
    async def sb_add(self, ctx: commands.Context, name: str, emoji: str, *, query: str = None):
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            suffix = Path(attachment.filename).suffix.lower()
            if suffix not in AUDIO_EXTS:
                return await ctx.send(
                    f'Unsupported file type. Attach an audio file '
                    f'({", ".join(sorted(AUDIO_EXTS))}).'
                )
            dest = SOUNDBOARD_DIR / f'{ctx.guild.id}_{name}{suffix}'
            # Delete old file if extension is changing to avoid orphans.
            old_entry = get_sound(ctx.guild.id, name)
            if old_entry and old_entry['file'] != str(dest):
                Path(old_entry['file']).unlink(missing_ok=True)
            await ctx.send('Saving attachment...')
            dest.write_bytes(await attachment.read())
            source_label = attachment.filename
            log.info('Soundboard add from attachment — guild %s name %s', ctx.guild.id, name)
        elif query:
            dest = SOUNDBOARD_DIR / f'{ctx.guild.id}_{name}.mp3'
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
            return await ctx.send(
                f'Provide a URL/search term or attach an audio file '
                f'({", ".join(sorted(AUDIO_EXTS))}).'
            )

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

        sound_file = Path(entry['file'])
        if not sound_file.exists():
            return await ctx.send(f'Sound file for **{name}** is missing.')

        log.info('Soundboard trigger — guild %s name %s (by %s)', ctx.guild.id, name, ctx.author)
        await play_with_interrupt(self.bot, ctx.guild.id, str(sound_file), ctx.channel)
        await ctx.send(f'Playing **{name}** {entry["emoji"]}.')

    # ── Listener ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        if not payload.guild_id:
            return

        panel = self._panels.get(payload.guild_id)
        if panel is None:
            return

        panel_msg, emoji_map = panel
        if payload.message_id != panel_msg.id:
            return

        emoji_str = str(payload.emoji)
        sound_name = emoji_map.get(emoji_str)
        if not sound_name:
            return

        guild   = self.bot.get_guild(payload.guild_id)
        channel = guild.get_channel(payload.channel_id) if guild else None
        member  = payload.member
        if guild is None or channel is None or member is None:
            return

        try:
            await panel_msg.remove_reaction(payload.emoji, member)
        except discord.HTTPException:
            pass

        self._reset_panel_timer(payload.guild_id)
        await self._play_from_reaction(guild, channel, member, sound_name)


async def setup(bot):
    await bot.add_cog(SoundboardCog(bot))
