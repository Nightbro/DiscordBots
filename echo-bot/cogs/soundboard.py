from __future__ import annotations

import re
from pathlib import Path

import discord
from discord.ext import commands

from utils.audio import AudioFileManager
from utils.config import PREFIX, SOUNDBOARD_DIR
from utils.guild_state import Track
from utils.i18n import t
from utils.message import MessageWriter
from utils.notifier import Notifier
from utils.soundboard_config import (
    add_sound,
    find_sound,
    get_sound,
    get_sound_path,
    get_sounds,
    remove_sound,
    set_short,
    sound_exists,
)
from utils.voice import VoiceStreamer

# Matches Unicode emoji (main planes + misc symbols) and Discord custom emoji
_EMOJI_RE = re.compile(
    '(?:<a?:[^:]+:\\d+>'
    '|[\U0001F000-\U0001FFFF]'
    '|[⌀-⯿]'
    ')'
)


def _parse_add_text(text: str) -> tuple[str, str, str] | None:
    """
    Parse 'name emoji [short]' from raw add text.
    Returns (name, emoji, short) — short may be empty — or None if no emoji found.
    """
    m = _EMOJI_RE.search(text)
    if m is None:
        return None
    name = text[:m.start()].strip()
    emoji = m.group()
    short = text[m.end():].strip()
    return name, emoji, short


class SoundboardCog(commands.Cog, name='Soundboard'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Maps message_id → guild_id so the reaction listener can find the panel
        self._panel_messages: dict[int, int] = {}

    def _notifier(self, ctx) -> Notifier:
        return Notifier(self.bot, ctx.guild.id)

    async def _ask_to_join(self, ctx) -> VoiceStreamer | None:
        gid = ctx.guild.id
        if ctx.author.voice is None:
            await self._notifier(ctx).error(ctx, t('common.error_no_voice', gid))
            return None
        streamer = VoiceStreamer(self.bot, gid)
        await streamer.join(ctx.author.voice.channel)
        return streamer

    # -----------------------------------------------------------------------
    # Events
    # -----------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild is None:
            return
        if not message.content.startswith(PREFIX):
            return

        rest = message.content[len(PREFIX):].strip()
        if not rest:
            return
        name = rest.split()[0].lower()

        # Don't intercept registered commands
        if self.bot.get_command(name):
            return

        # Case-insensitive lookup by full name OR short trigger
        result = find_sound(name)
        if result is None:
            return
        matched_name, _ = result

        gid = message.guild.id
        member = message.author

        if not isinstance(member, discord.Member) or member.voice is None:
            await message.channel.send(
                embed=MessageWriter.error(t('common.error_no_voice', gid))
            )
            return

        streamer = VoiceStreamer(self.bot, gid)
        await streamer.join(member.voice.channel)
        path = get_sound_path(matched_name)
        if path is None:
            return
        track = Track(title=f'SFX: {matched_name}', url=str(path), file_path=path)
        await streamer.interrupt(track)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.user_id == self.bot.user.id:
            return
        if payload.message_id not in self._panel_messages:
            return

        guild_id = self._panel_messages[payload.message_id]
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return

        member = guild.get_member(payload.user_id)
        if member is None or member.bot:
            return

        emoji = str(payload.emoji)
        sounds = get_sounds()

        target_name: str | None = None
        for name, meta in sounds.items():
            if meta.get('emoji') == emoji:
                target_name = name
                break

        if target_name is None:
            return

        if member.voice is None:
            return

        streamer = VoiceStreamer(self.bot, guild_id)
        await streamer.join(member.voice.channel)
        path = get_sound_path(target_name)
        if path is None:
            return
        track = Track(title=f'SFX: {target_name}', url=str(path), file_path=path)
        await streamer.interrupt(track)

        # Remove the user's reaction to keep the panel clean
        channel = guild.get_channel(payload.channel_id)
        if channel:
            try:
                msg = await channel.fetch_message(payload.message_id)
                await msg.remove_reaction(payload.emoji, member)
            except (discord.NotFound, discord.Forbidden):
                pass

    # -----------------------------------------------------------------------
    # Commands
    # -----------------------------------------------------------------------

    @commands.hybrid_group(name='sb', aliases=['soundboard'], invoke_without_command=True)
    async def sb(self, ctx: commands.Context) -> None:
        """Soundboard management."""
        gid = ctx.guild.id
        await ctx.send(embed=MessageWriter.info(t('soundboard.commands_title', gid), t('soundboard.hint', gid)))

    @sb.command(name='add')
    async def sb_add(self, ctx: commands.Context, *, text: str) -> None:
        """Add a sound: attach audio and type  name 💥 [short]"""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)

        parsed = _parse_add_text(text)
        if parsed is None:
            await notifier.error(ctx, t('soundboard.add_parse_error', gid))
            return
        name, emoji, short_raw = parsed

        if not name:
            await notifier.error(ctx, t('soundboard.add_no_name', gid))
            return

        if sound_exists(name):
            await notifier.error(
                ctx,
                t('soundboard.add_duplicate', gid, name=name),
                t('soundboard.add_duplicate_hint', gid, name=name),
            )
            return

        ext = _ext_from_ctx(ctx)
        filename = f'{name}{ext}'
        path = await AudioFileManager.receive_attachment(ctx, SOUNDBOARD_DIR, filename)
        if path is None:
            return

        assigned_short = short_raw if short_raw else name.replace(' ', '').lower()
        add_sound(name, filename, emoji, assigned_short)
        desc = t('soundboard.add_desc', gid, emoji=emoji, filename=filename)
        desc += f'\nShort trigger: `!{assigned_short}`'
        await notifier.success(ctx, t('soundboard.add_title', gid, name=name), desc)

    @sb.command(name='short')
    async def sb_short(self, ctx: commands.Context, *, text: str) -> None:
        """Change the short trigger for a sound: name new_short"""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)

        parts = text.strip().rsplit(maxsplit=1)
        if len(parts) < 2:
            await notifier.error(ctx, t('soundboard.short_usage', gid))
            return
        name, new_short = parts[0], parts[1]

        if not sound_exists(name):
            await notifier.error(ctx, t('soundboard.remove_not_found', gid, name=name))
            return

        set_short(name, new_short)
        await notifier.success(ctx, t('soundboard.short_done', gid, name=name, short=new_short))

    @sb.command(name='remove')
    async def sb_remove(self, ctx: commands.Context, name: str) -> None:
        """Remove a sound from the soundboard (also deletes the file)."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        meta = get_sound(name)
        if meta is None:
            await notifier.error(ctx, t('soundboard.remove_not_found', gid, name=name))
            return

        file_path = SOUNDBOARD_DIR / meta['file']
        if file_path.exists():
            file_path.unlink()

        remove_sound(name)
        await notifier.success(ctx, t('soundboard.remove_done', gid, name=name))

    @sb.command(name='play')
    async def sb_play(self, ctx: commands.Context, name: str) -> None:
        """Play a soundboard sound in your voice channel."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        streamer = await self._ask_to_join(ctx)
        if streamer is None:
            return
        path = get_sound_path(name)
        if path is None:
            await notifier.error(ctx, t('soundboard.play_not_found', gid, name=name))
            return
        track = Track(title=f'SFX: {name}', url=str(path), file_path=path)
        await streamer.interrupt(track)

    @sb.command(name='list')
    async def sb_list(self, ctx: commands.Context) -> None:
        """List all soundboard sounds."""
        sounds = get_sounds()
        await ctx.send(embed=MessageWriter.soundboard_panel(sounds, guild_id=ctx.guild.id))

    @sb.command(name='panel')
    async def sb_panel(self, ctx: commands.Context) -> None:
        """Post a reaction panel — react to play sounds."""
        sounds = get_sounds()
        embed = MessageWriter.soundboard_panel(sounds, guild_id=ctx.guild.id)
        embed.set_footer(text=t('soundboard.panel_footer', ctx.guild.id))
        msg = await ctx.send(embed=embed)

        self._panel_messages[msg.id] = ctx.guild.id
        for meta in sounds.values():
            try:
                await msg.add_reaction(meta['emoji'])
            except discord.HTTPException:
                pass


def _ext_from_ctx(ctx: commands.Context) -> str:
    attachments = getattr(getattr(ctx, 'message', None), 'attachments', [])
    if attachments:
        return Path(attachments[0].filename).suffix.lower()
    return '.mp3'


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SoundboardCog(bot))
