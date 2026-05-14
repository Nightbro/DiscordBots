from __future__ import annotations

import datetime
from pathlib import Path

import discord
from discord.ext import commands

from utils.audio import AudioFileManager
from utils.config import INTRO_ON_USER_JOIN
from utils.guild_state import Track
from utils.i18n import t
from utils.intro_config import (
    canonicalize_days,
    clear_trigger,
    get_auto_join,
    get_intro_file,
    get_user_entry,
    list_entries,
    parse_days,
    remove_override_entry,
    remove_schedule_entry,
    set_auto_join,
    set_default_entry,
    set_override_entry,
    set_schedule_entry,
    user_dir,
)
from utils.message import MessageWriter
from utils.voice import VoiceStreamer


def _trigger_label(entry: dict) -> str:
    """Build a human-readable summary of a user's intro config."""
    parts = []
    if 'default' in entry:
        parts.append(f'default: `{entry["default"]}`')
    schedule = entry.get('schedule', {})
    if schedule:
        parts.append('schedule: ' + ', '.join(f'{d}:`{f}`' for d, f in schedule.items()))
    overrides = entry.get('overrides', {})
    if overrides:
        parts.append('overrides: ' + ', '.join(f'{dt}:`{f}`' for dt, f in overrides.items()))
    return '\n'.join(parts) if parts else ''


def _entry_lines(entries: dict[str, dict], guild: discord.Guild) -> list[str]:
    """Format all user entries as display lines."""
    lines = []
    for uid_str, entry in entries.items():
        try:
            member = guild.get_member(int(uid_str))
            name = member.display_name if member else f'<id:{uid_str}>'
        except ValueError:
            name = uid_str
        label = _trigger_label(entry) or t('intro.no_intro_set')
        lines.append(f'**{name}**: {label}')
    return lines


class IntrosCog(commands.Cog, name='Intros'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _ask_to_join(self, ctx) -> VoiceStreamer | None:
        """Join the author's voice channel, or send an error if they aren't in one."""
        gid = ctx.guild.id
        if ctx.author.voice is None:
            await ctx.send(embed=MessageWriter.error(t('common.error_no_voice', gid)))
            return None
        streamer = VoiceStreamer(self.bot, gid)
        await streamer.join(ctx.author.voice.channel)
        return streamer

    async def _play_intro(self, guild_id: int, user_id: int, channel: discord.VoiceChannel) -> None:
        """Play the user's intro in the given channel (interrupts current playback)."""
        path = get_intro_file(user_id)
        if path is None:
            return
        streamer = VoiceStreamer(self.bot, guild_id)
        await streamer.join(channel)
        track = Track(title=f'Intro for <@{user_id}>', url=str(path), file_path=path)
        await streamer.interrupt(track)

    # -----------------------------------------------------------------------
    # Events
    # -----------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return

        # User joined a voice channel
        if after.channel is not None and before.channel != after.channel:
            if INTRO_ON_USER_JOIN:
                await self._play_intro(member.guild.id, member.id, after.channel)

    # -----------------------------------------------------------------------
    # !intro set (default)
    # -----------------------------------------------------------------------

    @commands.hybrid_group(name='intro', invoke_without_command=True)
    async def intro(self, ctx: commands.Context) -> None:
        """Intro sound management."""
        gid = ctx.guild.id
        await ctx.send(embed=MessageWriter.info(
            'Intro commands',
            t('intro.hint', gid),
        ))

    @intro.command(name='set')
    async def intro_set(self, ctx: commands.Context) -> None:
        """Set your default intro sound (attach an audio file)."""
        gid = ctx.guild.id
        uid = ctx.author.id
        dest_dir = user_dir(uid)
        filename = f'default{_ext_from_ctx(ctx)}'
        path = await AudioFileManager.receive_attachment(ctx, dest_dir, filename)
        if path is None:
            return
        set_default_entry(uid, path.name)
        await ctx.send(embed=MessageWriter.success(
            t('intro.set_title', gid),
            t('intro.set_desc', gid, filename=path.name),
        ))

    @intro.command(name='schedule')
    async def intro_schedule(self, ctx: commands.Context, days: str) -> None:
        """Set a scheduled intro for specific days (attach an audio file).

        days: comma-separated day names, e.g. `mon,fri` or `monday,friday`
        """
        gid = ctx.guild.id
        parsed = parse_days(days)
        if not parsed:
            await ctx.send(embed=MessageWriter.error(
                t('intro.invalid_days', gid),
                t('intro.days_label', gid),
            ))
            return

        uid = ctx.author.id
        canonical = canonicalize_days(parsed)
        label = '_'.join(canonical)
        dest_dir = user_dir(uid)
        filename = f'schedule_{label}{_ext_from_ctx(ctx)}'
        path = await AudioFileManager.receive_attachment(ctx, dest_dir, filename)
        if path is None:
            return
        set_schedule_entry(uid, canonical, path.name)
        days_str = ', '.join(canonical)
        await ctx.send(embed=MessageWriter.success(
            t('intro.schedule_title', gid, days=days_str),
            t('intro.schedule_desc', gid, filename=path.name),
        ))

    @intro.command(name='override')
    async def intro_override(self, ctx: commands.Context, date: str) -> None:
        """Set a one-off intro for a specific date (YYYY-MM-DD, attach an audio file)."""
        gid = ctx.guild.id
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            await ctx.send(embed=MessageWriter.error(t('intro.invalid_date', gid)))
            return

        uid = ctx.author.id
        dest_dir = user_dir(uid)
        filename = f'override_{date}{_ext_from_ctx(ctx)}'
        path = await AudioFileManager.receive_attachment(ctx, dest_dir, filename)
        if path is None:
            return
        set_override_entry(uid, date, path.name)
        await ctx.send(embed=MessageWriter.success(
            t('intro.override_title', gid, date=date),
            t('intro.override_desc', gid, filename=path.name),
        ))

    @intro.command(name='unschedule')
    async def intro_unschedule(self, ctx: commands.Context, days: str) -> None:
        """Remove scheduled intro entries for the given days."""
        gid = ctx.guild.id
        parsed = parse_days(days)
        if not parsed:
            await ctx.send(embed=MessageWriter.error(
                t('intro.invalid_days', gid),
                t('intro.days_label', gid),
            ))
            return
        removed = remove_schedule_entry(ctx.author.id, parsed)
        if removed:
            await ctx.send(embed=MessageWriter.success(
                t('intro.unschedule_removed', gid, days=', '.join(removed)),
            ))
        else:
            await ctx.send(embed=MessageWriter.error(t('intro.unschedule_not_found', gid)))

    @intro.command(name='clear')
    async def intro_clear(self, ctx: commands.Context) -> None:
        """Remove all your intro settings."""
        gid = ctx.guild.id
        if clear_trigger(ctx.author.id):
            await ctx.send(embed=MessageWriter.success(t('intro.clear_done', gid)))
        else:
            await ctx.send(embed=MessageWriter.info(t('intro.clear_nothing', gid)))

    @intro.command(name='list')
    async def intro_list(self, ctx: commands.Context) -> None:
        """List all users with intro configs on this server."""
        gid = ctx.guild.id
        entries = list_entries()
        if not entries:
            await ctx.send(embed=MessageWriter.info(t('intro.list_empty', gid)))
            return
        lines = _entry_lines(entries, ctx.guild)
        await ctx.send(embed=MessageWriter.info(t('intro.list_title', gid), '\n'.join(lines)))

    @intro.command(name='show')
    async def intro_show(self, ctx: commands.Context) -> None:
        """Show your current intro config."""
        gid = ctx.guild.id
        entry = get_user_entry(ctx.author.id)
        if not entry:
            await ctx.send(embed=MessageWriter.info(t('intro.show_none', gid)))
            return
        label = _trigger_label(entry) or t('intro.no_intro_set', gid)
        await ctx.send(embed=MessageWriter.info(
            t('intro.show_title', gid, name=ctx.author.display_name),
            label,
        ))

    @intro.command(name='trigger')
    async def intro_trigger(self, ctx: commands.Context) -> None:
        """Manually trigger your intro sound."""
        gid = ctx.guild.id
        streamer = await self._ask_to_join(ctx)
        if streamer is None:
            return
        path = get_intro_file(ctx.author.id)
        if path is None:
            await ctx.send(embed=MessageWriter.error(t('intro.trigger_no_file', gid)))
            return
        track = Track(title=f'Intro: {ctx.author.display_name}', url=str(path), file_path=path)
        await streamer.interrupt(track)
        await ctx.send(embed=MessageWriter.success(t('intro.trigger_playing', gid)))

    @intro.command(name='autojoin')
    async def intro_autojoin(self, ctx: commands.Context, enabled: bool) -> None:
        """Toggle whether the bot auto-joins when you connect to a voice channel."""
        gid = ctx.guild.id
        set_auto_join(ctx.author.id, enabled)
        key = 'intro.autojoin_enabled' if enabled else 'intro.autojoin_disabled'
        await ctx.send(embed=MessageWriter.success(t(key, gid)))


def _ext_from_ctx(ctx: commands.Context) -> str:
    """Return the file extension of the first attachment, defaulting to .mp3."""
    attachments = getattr(getattr(ctx, 'message', None), 'attachments', [])
    if attachments:
        return Path(attachments[0].filename).suffix.lower()
    return '.mp3'


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(IntrosCog(bot))
