import asyncio
import logging
import shutil
from pathlib import Path

import discord
from discord.ext import commands

from utils.config import INTRO_SOUNDS_DIR, _INTRO_FILE, _INTRO_ON_BOT_JOIN, _INTRO_ON_USER_JOIN
from utils.downloader import download_track, FFMPEG_OPTIONS
from utils.player import get_state, play_with_interrupt
from utils.intro_config import (
    load_intro_config, save_intro_config,
    get_intro_file, get_user_intro,
    get_auto_join, set_auto_join,
    parse_days, canonicalize_days,
    set_default_entry, set_schedule_entry, remove_schedule_entry, clear_trigger,
)

log = logging.getLogger('music-bot.intros')

_YES = '✅'
_NO  = '❌'


def _trigger_label(trigger: str, entry: dict) -> str:
    """Human-readable label for a trigger key."""
    if trigger == 'bot':
        return '🤖 Bot join'
    if trigger == 'user':
        return '👥 Any user'
    if trigger.startswith('user_'):
        return f'👤 {entry.get("member_name", trigger[5:])}'
    return trigger


def _entry_lines(trigger_key: str, entry: dict) -> list:
    """Return display lines for a trigger entry (handles both flat and structured formats)."""
    label    = _trigger_label(trigger_key, entry)
    schedule = entry.get('schedule', [])
    lines    = []

    if 'file' in entry:  # old flat format
        p       = Path(entry['file'])
        missing = ' *(file missing!)*' if not p.exists() else ''
        lines.append(f'{label}: `{p.name}` — `{entry["source"]}`{missing}')
        return lines

    default = entry.get('default')
    if default:
        p       = Path(default['file'])
        missing = ' *(file missing!)*' if not p.exists() else ''
        suffix  = ' (default)' if schedule else ''
        lines.append(f'{label}{suffix}: `{p.name}` — `{default["source"]}`{missing}')

    for sched in schedule:
        p       = Path(sched['file'])
        missing = ' *(file missing!)*' if not p.exists() else ''
        lines.append(f'  ↳ [{sched["days"]}]: `{p.name}` — `{sched["source"]}`{missing}')

    return lines


class IntrosCog(commands.Cog, name='Intros'):
    def __init__(self, bot):
        self.bot = bot

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _ask_to_join(self, ctx: commands.Context) -> bool:
        """Prompt the invoking user with ✅/❌ to decide whether the bot should join."""
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

    async def _resolve_trigger(self, ctx: commands.Context, trigger: str):
        """Return (trigger_key, member_or_None) or send an error and return None."""
        if trigger in ('bot', 'user'):
            return trigger, None
        try:
            member = await commands.MemberConverter().convert(ctx, trigger)
            return f'user_{member.id}', member
        except commands.MemberNotFound:
            await ctx.send('Trigger must be `bot`, `user`, or a @mention of a server member.')
            return None, None

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.group(name='intro', aliases=['in'], invoke_without_command=True)
    async def intro_group(self, ctx: commands.Context):
        await ctx.send(
            '**Intro commands:**\n'
            '`!intro set bot|user|@user <url>` — set the default intro (or attach MP3)\n'
            '`!intro schedule bot|user|@user <days> <url>` — set a day-specific override (or attach MP3)\n'
            '`!intro unschedule bot|user|@user <days>` — remove a day-specific override\n'
            '`!intro clear bot|user|@user` — remove all intros for this trigger\n'
            '`!intro list` — list all configured triggers\n'
            '`!intro show` — show bot/server-wide config and global flags\n'
            '`!intro rename bot|user|@user <name>` — give an intro a human-readable label\n'
            '`!intro trigger bot|user|@user` — manually play an intro\n'
            '`!intro autojoin on|off` — auto-join when first user enters a voice channel\n'
            '*Days: `MON` `SAT,SUN` `MON-FRI` `WEEKDAY` `WEEKEND`*'
        )

    @intro_group.command(name='set')
    async def intro_set(self, ctx: commands.Context, trigger: str, *, query: str = None):
        trigger_key, member = await self._resolve_trigger(ctx, trigger)
        if trigger_key is None:
            return

        if member:
            dest     = INTRO_SOUNDS_DIR / f'{ctx.guild.id}_user_{member.id}.mp3'
            dl_label = f'intro for **{member.display_name}**'
        else:
            dest     = INTRO_SOUNDS_DIR / f'{ctx.guild.id}_{trigger}.mp3'
            dl_label = f'**{trigger}**-join intro'

        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if not attachment.filename.lower().endswith('.mp3'):
                return await ctx.send('Only MP3 attachments are supported.')
            await ctx.send('Saving attachment...')
            dest.write_bytes(await attachment.read())
            source_label = attachment.filename
            log.info('Intro set from attachment — guild %s key %s: %s',
                     ctx.guild.id, trigger_key, source_label)
        elif query:
            await ctx.send(f'Downloading {dl_label}...')
            try:
                loop  = asyncio.get_event_loop()
                track = await loop.run_in_executor(None, download_track, query)
            except Exception as e:
                log.error('Intro download failed — guild %s key %s: %s',
                          ctx.guild.id, trigger_key, e, exc_info=True)
                return await ctx.send(f'Could not download: `{e}`')
            shutil.copy(track['file'], dest)
            source_label = query
            log.info('Intro set from URL — guild %s key %s: %s',
                     ctx.guild.id, trigger_key, source_label)
        else:
            return await ctx.send('Provide a URL/search term or attach an MP3 file.')

        set_default_entry(
            ctx.guild.id, trigger_key, str(dest), source_label,
            member_name=str(member) if member else None,
        )

        label = f'**{member.display_name}**' if member else f'**{trigger.capitalize()}-join**'
        await ctx.send(f'{label} intro set to `{dest.name}`.')

    @intro_group.command(name='schedule')
    async def intro_schedule(
        self, ctx: commands.Context, trigger: str, days: str, *, query: str = None
    ):
        """Add a day-specific intro override for a trigger."""
        trigger_key, member = await self._resolve_trigger(ctx, trigger)
        if trigger_key is None:
            return

        try:
            days_set   = parse_days(days)
            canon_days = canonicalize_days(days_set)
        except ValueError as e:
            return await ctx.send(f'Invalid day pattern: {e}')

        days_norm = canon_days.replace(',', '_')
        if member:
            dest     = INTRO_SOUNDS_DIR / f'{ctx.guild.id}_user_{member.id}_s_{days_norm}.mp3'
            dl_label = f'intro for **{member.display_name}** on {canon_days}'
        else:
            dest     = INTRO_SOUNDS_DIR / f'{ctx.guild.id}_{trigger}_s_{days_norm}.mp3'
            dl_label = f'**{trigger}**-join intro for {canon_days}'

        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if not attachment.filename.lower().endswith('.mp3'):
                return await ctx.send('Only MP3 attachments are supported.')
            await ctx.send('Saving attachment...')
            dest.write_bytes(await attachment.read())
            source_label = attachment.filename
            log.info('Schedule entry set from attachment — guild %s key %s days %s: %s',
                     ctx.guild.id, trigger_key, canon_days, source_label)
        elif query:
            await ctx.send(f'Downloading {dl_label}...')
            try:
                loop  = asyncio.get_event_loop()
                track = await loop.run_in_executor(None, download_track, query)
            except Exception as e:
                log.error('Schedule download failed — guild %s key %s days %s: %s',
                          ctx.guild.id, trigger_key, canon_days, e, exc_info=True)
                return await ctx.send(f'Could not download: `{e}`')
            shutil.copy(track['file'], dest)
            source_label = query
            log.info('Schedule entry set from URL — guild %s key %s days %s: %s',
                     ctx.guild.id, trigger_key, canon_days, source_label)
        else:
            return await ctx.send('Provide a URL/search term or attach an MP3 file.')

        set_schedule_entry(ctx.guild.id, trigger_key, days, str(dest), source_label)

        label = f'**{member.display_name}**' if member else f'**{trigger.capitalize()}-join**'
        await ctx.send(f'{label} intro for **{canon_days}** set to `{dest.name}`.')

    @intro_group.command(name='unschedule')
    async def intro_unschedule(self, ctx: commands.Context, trigger: str, *, days: str):
        """Remove a day-specific intro override for a trigger."""
        trigger_key, member = await self._resolve_trigger(ctx, trigger)
        if trigger_key is None:
            return

        try:
            days_set   = parse_days(days)
            canon_days = canonicalize_days(days_set)
        except ValueError as e:
            return await ctx.send(f'Invalid day pattern: {e}')

        removed = remove_schedule_entry(ctx.guild.id, trigger_key, days)

        if not removed:
            label = member.display_name if member else f'{trigger}-join'
            return await ctx.send(
                f'No schedule override for **{canon_days}** found on **{label}**.'
            )

        label = member.display_name if member else f'{trigger.capitalize()}-join'
        await ctx.send(f'**{label}** intro override for **{canon_days}** removed.')

    @intro_group.command(name='clear')
    async def intro_clear(self, ctx: commands.Context, trigger: str):
        trigger_key, member = await self._resolve_trigger(ctx, trigger)
        if trigger_key is None:
            return

        entry = clear_trigger(ctx.guild.id, trigger_key)

        if entry is None:
            label = member.display_name if member else f'{trigger}-join'
            return await ctx.send(f'No intro configured for **{label}**.')

        log.info('Intro cleared — guild %s key %s', ctx.guild.id, trigger_key)
        label = member.display_name if member else f'{trigger.capitalize()}-join'
        await ctx.send(f'**{label}** intro removed.')

    @intro_group.command(name='list')
    async def intro_list(self, ctx: commands.Context):
        """List every intro trigger configured for this server."""
        config    = load_intro_config()
        guild_cfg = config.get(str(ctx.guild.id), {})
        triggers  = {k: v for k, v in guild_cfg.items() if not k.startswith('_')}

        auto_join  = guild_cfg.get('_auto_join', False)
        auto_label = '✅ on' if auto_join else '❌ off'

        if not triggers:
            return await ctx.send(
                f'No intros configured for this server yet.\n*Auto-join: {auto_label}*'
            )

        lines = []
        for key, entry in triggers.items():
            lines.extend(_entry_lines(key, entry))

        await ctx.send(
            f'**Intro triggers ({len(triggers)}):**\n' + '\n'.join(lines) +
            f'\n*Auto-join: {auto_label}*'
        )

    @intro_group.command(name='show')
    async def intro_show(self, ctx: commands.Context):
        """Show bot/server-wide intro config and global enable flags."""
        config    = load_intro_config()
        guild_cfg = config.get(str(ctx.guild.id), {})

        lines = []
        for trigger, label in (('bot', 'Bot join'), ('user', 'Any user')):
            entry = guild_cfg.get(trigger)
            if not entry:
                fallback = f'fallback: `{_INTRO_FILE.name}`' if _INTRO_FILE.exists() else 'not set'
                lines.append(f'**{label}:** *(not configured — {fallback})*')
                continue

            schedule = entry.get('schedule', [])

            if 'file' in entry:  # flat format
                p       = Path(entry['file'])
                missing = ' *(file missing!)*' if not p.exists() else ''
                lines.append(f'**{label}:** `{p.name}` — `{entry["source"]}`{missing}')
            else:
                default = entry.get('default')
                if default:
                    p       = Path(default['file'])
                    missing = ' *(file missing!)*' if not p.exists() else ''
                    suffix  = ' (default)' if schedule else ''
                    lines.append(
                        f'**{label}{suffix}:** `{p.name}` — `{default["source"]}`{missing}'
                    )
                elif schedule:
                    lines.append(f'**{label}:** *(no default — schedule only)*')
                else:
                    fallback = f'fallback: `{_INTRO_FILE.name}`' if _INTRO_FILE.exists() else 'not set'
                    lines.append(f'**{label}:** *(empty — {fallback})*')

                for sched in schedule:
                    p       = Path(sched['file'])
                    missing = ' *(file missing!)*' if not p.exists() else ''
                    lines.append(
                        f'  ↳ [{sched["days"]}]: `{p.name}` — `{sched["source"]}`{missing}'
                    )

        per_user = [k for k in guild_cfg if k.startswith('user_')]
        if per_user:
            lines.append(f'*+ {len(per_user)} per-user intro(s) — use `!intro list` to see all*')

        active = []
        if _INTRO_ON_BOT_JOIN:
            active.append('bot join')
        if _INTRO_ON_USER_JOIN:
            active.append('user join')
        active_str = ', '.join(active) if active else 'none (both disabled in .env)'

        auto_join = guild_cfg.get('_auto_join', False)
        auto_str  = '**enabled**' if auto_join else 'disabled'

        await ctx.send(
            '**Intro config:**\n' + '\n'.join(lines) +
            f'\n*Global triggers enabled: {active_str}*' +
            f'\n*Auto-join on first user: {auto_str}*'
        )

    @intro_group.command(name='rename')
    async def intro_rename(self, ctx: commands.Context, trigger: str, *, name: str):
        """Give a human-readable label to an existing intro's source field."""
        trigger_key, member = await self._resolve_trigger(ctx, trigger)
        if trigger_key is None:
            return

        config = load_intro_config()
        gid    = str(ctx.guild.id)
        entry  = config.get(gid, {}).get(trigger_key)

        if not entry:
            label = member.display_name if member else f'{trigger}-join'
            return await ctx.send(f'No intro configured for **{label}**.')

        if 'file' in entry:  # flat format
            entry['source'] = name
        elif 'default' in entry:
            entry['default']['source'] = name
        else:
            return await ctx.send(
                f'No default intro to rename — set one first with `!intro set`.'
            )

        save_intro_config(config)
        log.info('Intro source renamed — guild %s key %s: %r', ctx.guild.id, trigger_key, name)

        display = member.display_name if member else trigger.capitalize() + '-join'
        await ctx.send(f'**{display}** intro label set to `{name}`.')

    @intro_group.command(name='trigger')
    async def intro_trigger(self, ctx: commands.Context, *, member_str: str):
        """Manually play an intro. Accepts: bot, user, or @mention."""
        member      = None
        trigger_key = None
        if member_str in ('bot', 'user'):
            trigger_key = member_str
        else:
            try:
                member = await commands.MemberConverter().convert(ctx, member_str)
            except commands.MemberNotFound:
                return await ctx.send(
                    'Could not find that member. Use `bot`, `user`, or a @mention.'
                )

        state = get_state(self.bot, ctx.guild.id)
        vc: discord.VoiceClient = state['voice_client']

        if not ctx.author.voice:
            await ctx.send("I will not listen to someone who doesn't even have the courage to show up.")
            return

        if vc is not None and vc.is_connected():
            if ctx.author.voice.channel != vc.channel:
                await ctx.send("Sorry, I cannot hear you — I am kinda busy.")
                return
        else:
            if not await self._ask_to_join(ctx):
                return
            state['voice_client'] = await ctx.author.voice.channel.connect()
            vc = state['voice_client']

        if trigger_key:
            intro   = get_intro_file(ctx.guild.id, trigger_key)
            display = trigger_key.capitalize() + '-join'
        else:
            intro   = get_user_intro(member.guild.id, member.id)
            display = member.display_name

        if not intro:
            return await ctx.send(f'No intro configured for **{display}**.')

        log.info('Manually triggering intro %s in guild %s (by %s)',
                 trigger_key or member, ctx.guild.id, ctx.author)
        await play_with_interrupt(self.bot, ctx.guild.id, str(intro), ctx.channel)
        await ctx.send(f'Playing **{display}** intro.')

    @intro_group.command(name='autojoin')
    async def intro_autojoin(self, ctx: commands.Context, state: str):
        """Enable or disable auto-joining when the first user enters a voice channel."""
        if state.lower() not in ('on', 'off'):
            return await ctx.send('Usage: `!intro autojoin on` or `!intro autojoin off`')
        enabled = state.lower() == 'on'
        set_auto_join(ctx.guild.id, enabled)
        status = 'enabled' if enabled else 'disabled'
        log.info('Auto-join %s for guild %s by %s', status, ctx.guild.id, ctx.author)
        await ctx.send(f'Auto-join **{status}**.')

    # ── Listener ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return
        if after.channel is None or before.channel == after.channel:
            return

        state = get_state(self.bot, member.guild.id)
        vc: discord.VoiceClient = state['voice_client']

        if get_auto_join(member.guild.id) and (vc is None or not vc.is_connected()):
            non_bot = [m for m in after.channel.members if not m.bot]
            if len(non_bot) == 1:
                log.info('Auto-joining channel %s in guild %s', after.channel, member.guild.id)
                state['voice_client'] = await after.channel.connect()
                vc = state['voice_client']

        if not _INTRO_ON_USER_JOIN:
            return
        if vc is None or not vc.is_connected() or vc.channel != after.channel:
            return
        intro = get_user_intro(member.guild.id, member.id)
        if not intro:
            return
        log.info('Playing user-join intro for %s in guild %s', member, member.guild.id)
        await play_with_interrupt(self.bot, member.guild.id, str(intro))


async def setup(bot):
    await bot.add_cog(IntrosCog(bot))
