from __future__ import annotations

from pathlib import Path

import discord
from discord.ext import commands

from utils.audio import AudioFileManager
from utils.config import SOUNDBOARD_DIR
from utils.guild_state import Track
from utils.message import MessageWriter
from utils.soundboard_config import (
    add_sound,
    get_sound,
    get_sound_path,
    get_sounds,
    remove_sound,
    sound_exists,
)
from utils.voice import VoiceStreamer

# Emoji pool used when auto-assigning an emoji to a new sound
_EMOJI_POOL = ['🔊', '💥', '📯', '🎺', '🎸', '🥁', '🎷', '🎻', '🔔', '🎹']


def _pick_emoji(sounds: dict) -> str:
    used = {m['emoji'] for m in sounds.values()}
    for e in _EMOJI_POOL:
        if e not in used:
            return e
    return '🔊'


class SoundboardCog(commands.Cog, name='Soundboard'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Maps message_id → guild_id so the reaction listener can find the panel
        self._panel_messages: dict[int, int] = {}

    async def _ask_to_join(self, ctx) -> VoiceStreamer | None:
        if ctx.author.voice is None:
            await ctx.send(embed=MessageWriter.error('You must be in a voice channel.'))
            return None
        streamer = VoiceStreamer(self.bot, ctx.guild.id)
        await streamer.join(ctx.author.voice.channel)
        return streamer

    # -----------------------------------------------------------------------
    # Events
    # -----------------------------------------------------------------------

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

        # Find the sound with this emoji
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
        await ctx.send(embed=MessageWriter.info(
            'Soundboard commands',
            '`add <name>` · `remove <name>` · `play <name>` · `list` · `panel`',
        ))

    @sb.command(name='add')
    async def sb_add(self, ctx: commands.Context, name: str, emoji: str = '') -> None:
        """Add a sound to the soundboard (attach an audio file)."""
        if sound_exists(name):
            await ctx.send(embed=MessageWriter.error(
                f'Sound **{name}** already exists.',
                'Use `!sb remove {name}` first.',
            ))
            return

        dest_dir = SOUNDBOARD_DIR
        ext = _ext_from_ctx(ctx)
        filename = f'{name}{ext}'
        path = await AudioFileManager.receive_attachment(ctx, dest_dir, filename)
        if path is None:
            return

        assigned_emoji = emoji.strip() if emoji.strip() else _pick_emoji(get_sounds())
        add_sound(name, filename, assigned_emoji)
        await ctx.send(embed=MessageWriter.success(
            f'Added sound **{name}**',
            f'Emoji: {assigned_emoji}  File: `{filename}`',
        ))

    @sb.command(name='remove')
    async def sb_remove(self, ctx: commands.Context, name: str) -> None:
        """Remove a sound from the soundboard (also deletes the file)."""
        meta = get_sound(name)
        if meta is None:
            await ctx.send(embed=MessageWriter.error(f'Sound **{name}** not found.'))
            return

        # Delete file
        file_path = SOUNDBOARD_DIR / meta['file']
        if file_path.exists():
            file_path.unlink()

        remove_sound(name)
        await ctx.send(embed=MessageWriter.success(f'Removed sound **{name}**.'))

    @sb.command(name='play')
    async def sb_play(self, ctx: commands.Context, name: str) -> None:
        """Play a soundboard sound in your voice channel."""
        streamer = await self._ask_to_join(ctx)
        if streamer is None:
            return
        path = get_sound_path(name)
        if path is None:
            await ctx.send(embed=MessageWriter.error(f'Sound **{name}** not found or file missing.'))
            return
        track = Track(title=f'SFX: {name}', url=str(path), file_path=path)
        await streamer.interrupt(track)

    @sb.command(name='list')
    async def sb_list(self, ctx: commands.Context) -> None:
        """List all soundboard sounds."""
        sounds = get_sounds()
        await ctx.send(embed=MessageWriter.soundboard_panel(sounds))

    @sb.command(name='panel')
    async def sb_panel(self, ctx: commands.Context) -> None:
        """Post a reaction panel — react to play sounds."""
        sounds = get_sounds()
        embed = MessageWriter.soundboard_panel(sounds)
        embed.set_footer(text='React to play a sound')
        msg = await ctx.send(embed=embed)

        # Register message and add reactions
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
