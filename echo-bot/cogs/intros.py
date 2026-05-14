from __future__ import annotations

import datetime
from pathlib import Path

import discord
from discord.ext import commands

from utils.audio import AudioFileManager
from utils.config import INTRO_ON_USER_JOIN
from utils.guild_state import Track
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

_DAYS_LABEL = 'mon · tue · wed · thu · fri · sat · sun'


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
    return '\n'.join(parts) if parts else 'No intro set.'


def _entry_lines(entries: dict[str, dict], guild: discord.Guild) -> list[str]:
    """Format all user entries as display lines."""
    lines = []
    for uid_str, entry in entries.items():
        try:
            member = guild.get_member(int(uid_str))
            name = member.display_name if member else f'<id:{uid_str}>'
        except ValueError:
            name = uid_str
        lines.append(f'**{name}**: {_trigger_label(entry)}')
    return lines


class IntrosCog(commands.Cog, name='Intros'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _ask_to_join(self, ctx) -> VoiceStreamer | None:
        """Join the author's voice channel, or send an error if they aren't in one."""
        if ctx.author.voice is None:
            await ctx.send(embed=MessageWriter.error('You must be in a voice channel.'))
            return None
        streamer = VoiceStreamer(self.bot, ctx.guild.id)
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
        await ctx.send(embed=MessageWriter.info(
            'Intro commands',
            '`set` · `schedule` · `override` · `unschedule` · `clear` · `list` · `show` · `trigger` · `autojoin`',
        ))

    @intro.command(name='set')
    async def intro_set(self, ctx: commands.Context) -> None:
        """Set your default intro sound (attach an audio file)."""
        uid = ctx.author.id
        dest_dir = user_dir(uid)
        filename = f'default{_ext_from_ctx(ctx)}'
        path = await AudioFileManager.receive_attachment(ctx, dest_dir, filename)
        if path is None:
            return
        set_default_entry(uid, path.name)
        await ctx.send(embed=MessageWriter.success('Default intro set.', f'File: `{path.name}`'))

    @intro.command(name='schedule')
    async def intro_schedule(self, ctx: commands.Context, days: str) -> None:
        """Set a scheduled intro for specific days (attach an audio file).

        days: comma-separated day names, e.g. `mon,fri` or `monday,friday`
        """
        parsed = parse_days(days)
        if not parsed:
            await ctx.send(embed=MessageWriter.error(
                'Invalid days.',
                f'Use: {_DAYS_LABEL}',
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
            f'Schedule set for {days_str}.',
            f'File: `{path.name}`',
        ))

    @intro.command(name='override')
    async def intro_override(self, ctx: commands.Context, date: str) -> None:
        """Set a one-off intro for a specific date (YYYY-MM-DD, attach an audio file)."""
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            await ctx.send(embed=MessageWriter.error('Invalid date. Use YYYY-MM-DD format.'))
            return

        uid = ctx.author.id
        dest_dir = user_dir(uid)
        filename = f'override_{date}{_ext_from_ctx(ctx)}'
        path = await AudioFileManager.receive_attachment(ctx, dest_dir, filename)
        if path is None:
            return
        set_override_entry(uid, date, path.name)
        await ctx.send(embed=MessageWriter.success(
            f'Override set for {date}.',
            f'File: `{path.name}`',
        ))

    @intro.command(name='unschedule')
    async def intro_unschedule(self, ctx: commands.Context, days: str) -> None:
        """Remove scheduled intro entries for the given days."""
        parsed = parse_days(days)
        if not parsed:
            await ctx.send(embed=MessageWriter.error(
                'Invalid days.',
                f'Use: {_DAYS_LABEL}',
            ))
            return
        removed = remove_schedule_entry(ctx.author.id, parsed)
        if removed:
            await ctx.send(embed=MessageWriter.success(
                'Unscheduled: ' + ', '.join(removed),
            ))
        else:
            await ctx.send(embed=MessageWriter.error('No matching schedule entries found.'))

    @intro.command(name='clear')
    async def intro_clear(self, ctx: commands.Context) -> None:
        """Remove all your intro settings."""
        if clear_trigger(ctx.author.id):
            await ctx.send(embed=MessageWriter.success('Your intro config has been cleared.'))
        else:
            await ctx.send(embed=MessageWriter.info('You had no intro config to clear.'))

    @intro.command(name='list')
    async def intro_list(self, ctx: commands.Context) -> None:
        """List all users with intro configs on this server."""
        entries = list_entries()
        if not entries:
            await ctx.send(embed=MessageWriter.info('No intros configured yet.'))
            return
        lines = _entry_lines(entries, ctx.guild)
        await ctx.send(embed=MessageWriter.info('Intro configs', '\n'.join(lines)))

    @intro.command(name='show')
    async def intro_show(self, ctx: commands.Context) -> None:
        """Show your current intro config."""
        entry = get_user_entry(ctx.author.id)
        if not entry:
            await ctx.send(embed=MessageWriter.info('You have no intro configured.'))
            return
        await ctx.send(embed=MessageWriter.info(
            f'{ctx.author.display_name}\'s intro',
            _trigger_label(entry),
        ))

    @intro.command(name='trigger')
    async def intro_trigger(self, ctx: commands.Context) -> None:
        """Manually trigger your intro sound."""
        streamer = await self._ask_to_join(ctx)
        if streamer is None:
            return
        path = get_intro_file(ctx.author.id)
        if path is None:
            await ctx.send(embed=MessageWriter.error('You have no intro file set for today.'))
            return
        track = Track(title=f'Intro: {ctx.author.display_name}', url=str(path), file_path=path)
        await streamer.interrupt(track)
        await ctx.send(embed=MessageWriter.success('Playing your intro.'))

    @intro.command(name='autojoin')
    async def intro_autojoin(self, ctx: commands.Context, enabled: bool) -> None:
        """Toggle whether the bot auto-joins when you connect to a voice channel."""
        set_auto_join(ctx.author.id, enabled)
        state = 'enabled' if enabled else 'disabled'
        await ctx.send(embed=MessageWriter.success(f'Auto-join {state}.'))


def _ext_from_ctx(ctx: commands.Context) -> str:
    """Return the file extension of the first attachment, defaulting to .mp3."""
    attachments = getattr(getattr(ctx, 'message', None), 'attachments', [])
    if attachments:
        return Path(attachments[0].filename).suffix.lower()
    return '.mp3'


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(IntrosCog(bot))
