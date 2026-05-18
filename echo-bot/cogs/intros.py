from __future__ import annotations

import logging
import shutil
from pathlib import Path

import discord
from discord.ext import commands

from utils.audio import AudioFileManager
from utils.config import INTRO_ON_BOT_JOIN, INTRO_ON_USER_JOIN, INTRO_SOUNDS_DIR
from utils.downloader import Downloader
from utils.guild_state import Track
from utils.i18n import t
from utils.intro_config import (
    canonicalize_days,
    clear_trigger,
    get_intro_file,
    get_user_intro,
    list_entries,
    parse_days,
    remove_schedule_entry,
    rename_entry,
    set_default_entry,
    set_schedule_entry,
)
from utils.message import MessageWriter
from utils.notifier import Notifier
from utils.voice import VoiceStreamer

log = logging.getLogger(__name__)


def _trigger_label(trigger_key: str, entry: dict, gid: int) -> str:
    """Human-readable label for a trigger key."""
    if trigger_key == 'bot':
        return t('intro.trigger_label_bot', gid)
    if trigger_key == 'user':
        return t('intro.trigger_label_user', gid)
    if trigger_key.startswith('user_'):
        return entry.get('member_name') or trigger_key[5:]
    return trigger_key


def _entry_lines(trigger_key: str, entry: dict, gid: int) -> list[str]:
    """Return display lines for a trigger entry."""
    label = _trigger_label(trigger_key, entry, gid)
    schedule = entry.get('schedule', [])
    lines: list[str] = []

    default = entry.get('default')
    if default:
        p = Path(default['file'])
        missing = ' *(file missing!)*' if not p.exists() else ''
        suffix = ' (default)' if schedule else ''
        lines.append(f'**{label}{suffix}:** `{p.name}` — `{default["source"]}`{missing}')

    for sched in schedule:
        p = Path(sched['file'])
        missing = ' *(file missing!)*' if not p.exists() else ''
        lines.append(f'  ↳ [{sched["days"]}]: `{p.name}` — `{sched["source"]}`{missing}')

    return lines


class IntrosCog(commands.Cog, name='Intros'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _notifier(self, ctx) -> Notifier:
        return Notifier(self.bot, ctx.guild.id)

    async def _resolve_trigger(
        self, ctx: commands.Context, trigger: str
    ) -> tuple[str, discord.Member | None] | tuple[None, None]:
        """Return (trigger_key, member_or_None), or (None, None) on error."""
        if trigger in ('bot', 'user'):
            return trigger, None
        try:
            member = await commands.MemberConverter().convert(ctx, trigger)
            return f'user_{member.id}', member
        except commands.MemberNotFound:
            gid = ctx.guild.id
            await self._notifier(ctx).error(ctx, t('intro.invalid_trigger', gid))
            return None, None

    async def _save_audio(
        self, ctx: commands.Context, dest: Path, query: str | None
    ) -> tuple[str, str] | tuple[None, None]:
        """Save audio from attachment or URL to dest. Returns (dest_path_str, source_label) or (None, None)."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)

        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            suffix = Path(attachment.filename).suffix.lower()
            if not AudioFileManager.is_valid_audio(attachment.filename):
                await notifier.error(ctx, t('intro.unsupported_ext', gid))
                return None, None
            final_dest = dest.with_suffix(suffix)
            final_dest.write_bytes(await attachment.read())
            return str(final_dest), attachment.filename

        if query:
            final_dest = dest.with_suffix('.mp3')
            try:
                track = await Downloader.resolve(query)
                await Downloader.download(track)
                shutil.copy(str(track.file_path), str(final_dest))
            except Exception as exc:
                log.error('Intro download failed: %s', exc)
                await notifier.error(ctx, t('intro.download_failed', gid), str(exc))
                return None, None
            return str(final_dest), query

        await notifier.error(ctx, t('intro.attach_or_url', gid))
        return None, None

    async def _play_intro(self, guild_id: int, trigger_key: str) -> None:
        """Play a trigger's intro in the current voice channel (interrupt)."""
        path = get_intro_file(guild_id, trigger_key)
        if not path:
            return
        streamer = VoiceStreamer(self.bot, guild_id)
        track = Track(title=f'Intro: {trigger_key}', url=str(path), file_path=path)
        await streamer.interrupt(track)

    async def _play_user_intro(
        self, guild_id: int, member_id: int, channel: discord.VoiceChannel
    ) -> None:
        """Play the best intro for a member joining voice."""
        path = get_user_intro(guild_id, member_id)
        if not path:
            return
        streamer = VoiceStreamer(self.bot, guild_id)
        await streamer.join(channel)
        track = Track(title=f'Intro: user_{member_id}', url=str(path), file_path=path)
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
        # Bot itself joined a channel → play bot-join intro
        if member.id == self.bot.user.id:
            if after.channel is not None and before.channel != after.channel:
                if INTRO_ON_BOT_JOIN:
                    await self._play_intro(member.guild.id, 'bot')
            return

        if member.bot:
            return

        # Non-bot user joined a channel → play user intro
        if after.channel is not None and before.channel != after.channel:
            if INTRO_ON_USER_JOIN:
                await self._play_user_intro(member.guild.id, member.id, after.channel)

    # -----------------------------------------------------------------------
    # Commands
    # -----------------------------------------------------------------------

    @commands.hybrid_group(name='intro', invoke_without_command=True)
    async def intro(self, ctx: commands.Context) -> None:
        """Intro sound management."""
        gid = ctx.guild.id
        await ctx.send(embed=MessageWriter.info(t('intro.commands_title', gid), t('intro.hint', gid)))

    @intro.command(name='set')
    async def intro_set(
        self, ctx: commands.Context, trigger: str, *, query: str = ''
    ) -> None:
        """Set the default intro for a trigger (bot/user/@member). Attach audio or provide URL."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        trigger_key, member = await self._resolve_trigger(ctx, trigger)
        if trigger_key is None:
            return

        label = _trigger_label(trigger_key, {}, gid)
        if member:
            label = member.display_name

        stem = INTRO_SOUNDS_DIR / f'{gid}_{trigger_key}'
        file_path, source = await self._save_audio(ctx, stem, query or None)
        if file_path is None:
            return

        set_default_entry(gid, trigger_key, file_path, source,
                          member_name=str(member) if member else None)
        await notifier.success(
            ctx,
            t('intro.set_title', gid, label=label),
            t('intro.set_desc', gid, filename=Path(file_path).name),
        )

    @intro.command(name='schedule')
    async def intro_schedule(
        self, ctx: commands.Context, trigger: str, days: str, *, query: str = ''
    ) -> None:
        """Set a day-specific intro override for a trigger. Attach audio or provide URL.

        days: MON  SAT,SUN  MON-FRI  WEEKDAY  WEEKEND
        """
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        trigger_key, member = await self._resolve_trigger(ctx, trigger)
        if trigger_key is None:
            return

        try:
            days_set = parse_days(days)
            canon = canonicalize_days(days_set)
        except ValueError as exc:
            await notifier.error(ctx, t('intro.invalid_days', gid), str(exc))
            return

        label = member.display_name if member else _trigger_label(trigger_key, {}, gid)
        days_norm = canon.replace(',', '_')
        stem = INTRO_SOUNDS_DIR / f'{gid}_{trigger_key}_s_{days_norm}'
        file_path, source = await self._save_audio(ctx, stem, query or None)
        if file_path is None:
            return

        set_schedule_entry(gid, trigger_key, days, file_path, source)
        await notifier.success(
            ctx,
            t('intro.schedule_title', gid, label=label, days=canon),
            t('intro.set_desc', gid, filename=Path(file_path).name),
        )

    @intro.command(name='unschedule')
    async def intro_unschedule(
        self, ctx: commands.Context, trigger: str, *, days: str
    ) -> None:
        """Remove a day-specific intro override for a trigger."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        trigger_key, member = await self._resolve_trigger(ctx, trigger)
        if trigger_key is None:
            return

        try:
            days_set = parse_days(days)
            canon = canonicalize_days(days_set)
        except ValueError as exc:
            await notifier.error(ctx, t('intro.invalid_days', gid), str(exc))
            return

        label = member.display_name if member else _trigger_label(trigger_key, {}, gid)
        removed = remove_schedule_entry(gid, trigger_key, days)
        if not removed:
            await notifier.error(ctx, t('intro.unschedule_not_found', gid, days=canon, label=label))
            return
        await notifier.success(ctx, t('intro.unschedule_done', gid, days=canon, label=label))

    @intro.command(name='clear')
    async def intro_clear(self, ctx: commands.Context, trigger: str) -> None:
        """Remove all intros for a trigger (bot/user/@member)."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        trigger_key, member = await self._resolve_trigger(ctx, trigger)
        if trigger_key is None:
            return

        label = member.display_name if member else _trigger_label(trigger_key, {}, gid)
        entry = clear_trigger(gid, trigger_key)
        if entry is None:
            await notifier.info(ctx, t('intro.clear_nothing', gid, label=label))
            return
        await notifier.success(ctx, t('intro.clear_done', gid, label=label))

    @intro.command(name='rename')
    async def intro_rename(
        self, ctx: commands.Context, trigger: str, *, name: str
    ) -> None:
        """Give a human-readable label to a trigger's default intro."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        trigger_key, member = await self._resolve_trigger(ctx, trigger)
        if trigger_key is None:
            return

        label = member.display_name if member else _trigger_label(trigger_key, {}, gid)
        ok = rename_entry(gid, trigger_key, name)
        if not ok:
            await notifier.error(ctx, t('intro.rename_not_found', gid, label=label))
            return
        await notifier.success(ctx, t('intro.rename_done', gid, label=label, name=name))

    @intro.command(name='list')
    async def intro_list(self, ctx: commands.Context) -> None:
        """List all intro triggers configured for this server."""
        gid = ctx.guild.id
        entries = list_entries(gid)
        if not entries:
            await ctx.send(embed=MessageWriter.info(t('intro.list_empty', gid)))
            return
        lines: list[str] = []
        for key, entry in entries.items():
            lines.extend(_entry_lines(key, entry, gid))
        count = len(entries)
        await ctx.send(embed=MessageWriter.info(t('intro.list_title', gid, count=count), '\n'.join(lines)))

    @intro.command(name='show')
    async def intro_show(self, ctx: commands.Context) -> None:
        """Show bot/user intro config and global flags for this server."""
        gid = ctx.guild.id
        entries = list_entries(gid)
        lines: list[str] = []

        for trigger_key in ('bot', 'user'):
            entry = entries.get(trigger_key)
            label = _trigger_label(trigger_key, {}, gid)
            if not entry:
                lines.append(f'**{label}:** {t("intro.show_not_configured", gid)}')
                continue
            schedule = entry.get('schedule', [])
            default = entry.get('default')
            if default:
                p = Path(default['file'])
                missing = ' *(file missing!)*' if not p.exists() else ''
                suffix = ' (default)' if schedule else ''
                lines.append(f'**{label}{suffix}:** `{p.name}` — `{default["source"]}`{missing}')
            elif schedule:
                lines.append(f'**{label}:** {t("intro.show_no_default", gid)}')
            else:
                lines.append(f'**{label}:** {t("intro.show_not_configured", gid)}')
            for sched in schedule:
                p = Path(sched['file'])
                missing = ' *(file missing!)*' if not p.exists() else ''
                lines.append(f'  ↳ [{sched["days"]}]: `{p.name}` — `{sched["source"]}`{missing}')

        per_user = [k for k in entries if k.startswith('user_')]
        if per_user:
            lines.append(t('intro.show_per_user', gid, count=len(per_user)))

        await ctx.send(embed=MessageWriter.info(t('intro.show_title', gid), '\n'.join(lines) if lines else t('intro.list_empty', gid)))

    @intro.command(name='trigger')
    async def intro_trigger(
        self, ctx: commands.Context, *, trigger: str
    ) -> None:
        """Manually play an intro. Accepts: bot, user, or @mention."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)

        if trigger in ('bot', 'user'):
            trigger_key = trigger
            member = None
        else:
            try:
                member = await commands.MemberConverter().convert(ctx, trigger)
                trigger_key = f'user_{member.id}'
            except commands.MemberNotFound:
                await notifier.error(ctx, t('intro.invalid_trigger', gid))
                return

        if ctx.author.voice is None:
            await notifier.error(ctx, t('common.error_no_voice', gid))
            return

        streamer = VoiceStreamer(self.bot, gid)
        await streamer.join(ctx.author.voice.channel)

        if member:
            path = get_user_intro(gid, member.id)
            label = member.display_name
        else:
            path = get_intro_file(gid, trigger_key)
            label = _trigger_label(trigger_key, {}, gid)

        if not path:
            await notifier.error(ctx, t('intro.trigger_no_file', gid, label=label))
            return

        track = Track(title=f'Intro: {label}', url=str(path), file_path=path)
        await streamer.interrupt(track)
        await notifier.success(ctx, t('intro.trigger_playing', gid, label=label))

    @intro.command(name='autojoin')
    async def intro_autojoin(self, ctx: commands.Context, state: str) -> None:
        """Toggle whether the bot auto-joins when the first user enters a voice channel."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        if state.lower() not in ('on', 'off'):
            await notifier.error(ctx, t('intro.autojoin_usage', gid))
            return
        from utils.guild_config import set_setting
        enabled = state.lower() == 'on'
        set_setting(gid, 'auto_join', enabled)
        msg_key = 'intro.autojoin_enabled' if enabled else 'intro.autojoin_disabled'
        await notifier.success(ctx, t(msg_key, gid))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(IntrosCog(bot))
