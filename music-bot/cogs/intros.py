import asyncio
import logging
import shutil
from pathlib import Path

import discord
from discord.ext import commands

from utils.config import INTRO_SOUNDS_DIR, _INTRO_FILE, _INTRO_ON_BOT_JOIN, _INTRO_ON_USER_JOIN
from utils.downloader import download_track, FFMPEG_OPTIONS
from utils.player import get_state
from utils.intro_config import (
    load_intro_config, save_intro_config, get_intro_file, get_user_intro,
    get_auto_join, set_auto_join,
)

log = logging.getLogger('music-bot.intros')

_YES = '✅'
_NO  = '❌'
_NO_REACTION = ('🇳', '🇴')  # react N O to reject a command


def _trigger_label(trigger: str, entry: dict) -> str:
    """Human-readable label for a trigger key."""
    if trigger == 'bot':
        return '🤖 Bot join'
    if trigger == 'user':
        return '👥 Any user'
    if trigger.startswith('user_'):
        return f'👤 {entry.get("member_name", trigger[5:])}'
    return trigger


class IntrosCog(commands.Cog, name='Intros'):
    def __init__(self, bot):
        self.bot = bot

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _reject_not_in_channel(self, ctx: commands.Context):
        """React 🇳🇴 to the command message when the invoker isn't in the bot's voice channel."""
        for emoji in _NO_REACTION:
            await ctx.message.add_reaction(emoji)

    async def _ask_to_join(self, ctx: commands.Context) -> bool:
        """Prompt the invoking user with ✅/❌ to decide whether the bot should join.

        Edits the prompt message to reflect the outcome and cleans up all reactions.
        Returns True only if the user explicitly confirmed within 30 seconds.
        """
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

        # Remove user's reaction (requires Manage Messages; ignore if missing)
        if reaction is not None:
            try:
                await msg.remove_reaction(reaction.emoji, ctx.author)
            except discord.Forbidden:
                pass

        # Always remove the bot's own reactions
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

    @commands.group(name='intro', aliases=['in'], invoke_without_command=True)
    async def intro_group(self, ctx: commands.Context):
        await ctx.send(
            '**Intro commands:**\n'
            '`!intro set bot <url>` — set bot-join intro (or attach MP3)\n'
            '`!intro set user <url>` — set intro for any user joining (or attach MP3)\n'
            '`!intro set @user <url>` — set intro for a specific user (or attach MP3)\n'
            '`!intro clear bot` — remove bot-join intro\n'
            '`!intro clear user` — remove server-wide user-join intro\n'
            '`!intro clear @user` — remove a specific user\'s intro\n'
            '`!intro list` — list all configured triggers\n'
            '`!intro show` — show bot/server-wide config and global flags\n'
            '`!intro rename bot|user|@user <name>` — give an intro a human-readable label\n'
            '`!intro trigger @user` — manually play a user\'s intro\n'
            '`!intro autojoin on|off` — auto-join when first user enters a voice channel'
        )

    @intro_group.command(name='set')
    async def intro_set(self, ctx: commands.Context, trigger: str, *, query: str = None):
        member: discord.Member | None = None
        if trigger not in ('bot', 'user'):
            try:
                member = await commands.MemberConverter().convert(ctx, trigger)
            except commands.MemberNotFound:
                return await ctx.send(
                    'Trigger must be `bot`, `user`, or a @mention of a server member.'
                )

        if member:
            trigger_key = f'user_{member.id}'
            dest        = INTRO_SOUNDS_DIR / f'{ctx.guild.id}_user_{member.id}.mp3'
            dl_label    = f'intro for **{member.display_name}**'
        else:
            trigger_key = trigger
            dest        = INTRO_SOUNDS_DIR / f'{ctx.guild.id}_{trigger}.mp3'
            dl_label    = f'**{trigger}**-join intro'

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

        config = load_intro_config()
        entry  = {'file': str(dest), 'source': source_label}
        if member:
            entry['member_name'] = str(member)
        config.setdefault(str(ctx.guild.id), {})[trigger_key] = entry
        save_intro_config(config)

        label = f'**{member.display_name}**' if member else f'**{trigger.capitalize()}-join**'
        await ctx.send(f'{label} intro set to `{dest.name}`.')

    @intro_group.command(name='clear')
    async def intro_clear(self, ctx: commands.Context, trigger: str):
        member: discord.Member | None = None
        if trigger not in ('bot', 'user'):
            try:
                member = await commands.MemberConverter().convert(ctx, trigger)
            except commands.MemberNotFound:
                return await ctx.send(
                    'Trigger must be `bot`, `user`, or a @mention of a server member.'
                )

        trigger_key = f'user_{member.id}' if member else trigger
        config      = load_intro_config()
        gid         = str(ctx.guild.id)
        entry       = config.get(gid, {}).pop(trigger_key, None)

        if not entry:
            label = member.display_name if member else f'{trigger}-join'
            return await ctx.send(f'No intro configured for **{label}**.')

        Path(entry['file']).unlink(missing_ok=True)
        save_intro_config(config)
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
            p       = Path(entry['file'])
            missing = ' *(file missing!)*' if not p.exists() else ''
            label   = _trigger_label(key, entry)
            lines.append(f'{label}: `{p.name}` — `{entry["source"]}`{missing}')

        await ctx.send(
            f'**Intro triggers ({len(lines)}):**\n' + '\n'.join(lines) +
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
            if entry:
                p       = Path(entry['file'])
                missing = ' *(file missing!)*' if not p.exists() else ''
                lines.append(f'**{label}:** `{p.name}` — `{entry["source"]}`{missing}')
            else:
                fallback = f'fallback: `{_INTRO_FILE.name}`' if _INTRO_FILE.exists() else 'not set'
                lines.append(f'**{label}:** *(not configured — {fallback})*')

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
        member: discord.Member | None = None
        if trigger not in ('bot', 'user'):
            try:
                member = await commands.MemberConverter().convert(ctx, trigger)
            except commands.MemberNotFound:
                return await ctx.send(
                    'Trigger must be `bot`, `user`, or a @mention of a server member.'
                )

        trigger_key = f'user_{member.id}' if member else trigger
        config      = load_intro_config()
        gid         = str(ctx.guild.id)
        entry       = config.get(gid, {}).get(trigger_key)

        if not entry:
            label = member.display_name if member else f'{trigger}-join'
            return await ctx.send(f'No intro configured for **{label}**.')

        entry['source'] = name
        save_intro_config(config)
        log.info('Intro source renamed — guild %s key %s: %r', ctx.guild.id, trigger_key, name)

        display = member.display_name if member else trigger.capitalize() + '-join'
        await ctx.send(f'**{display}** intro label set to `{name}`.')

    @intro_group.command(name='trigger')
    async def intro_trigger(self, ctx: commands.Context, *, member_str: str):
        """Manually play the intro for a specific user."""
        try:
            member = await commands.MemberConverter().convert(ctx, member_str)
        except commands.MemberNotFound:
            return await ctx.send('Could not find that member.')

        state = get_state(self.bot, ctx.guild.id)
        vc: discord.VoiceClient = state['voice_client']

        if vc is None or not vc.is_connected():
            if not await self._ask_to_join(ctx):
                return
            if not ctx.author.voice:
                await self._reject_not_in_channel(ctx)
                return
            state['voice_client'] = await ctx.author.voice.channel.connect()
            vc = state['voice_client']
        elif not ctx.author.voice or ctx.author.voice.channel != vc.channel:
            await self._reject_not_in_channel(ctx)
            return

        if vc.is_playing() or vc.is_paused():
            return await ctx.send('Cannot play intro while audio is already playing.')

        intro = get_user_intro(member.guild.id, member.id)
        if not intro:
            return await ctx.send(f'No intro configured for **{member.display_name}**.')

        log.info('Manually triggering intro for %s in guild %s (by %s)',
                 member, ctx.guild.id, ctx.author)
        vc.play(discord.FFmpegPCMAudio(str(intro), **FFMPEG_OPTIONS))
        await ctx.send(f'Playing intro for **{member.display_name}**.')

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

        # Auto-join: connect when this is the first non-bot member in the channel
        if get_auto_join(member.guild.id) and (vc is None or not vc.is_connected()):
            non_bot = [m for m in after.channel.members if not m.bot]
            if len(non_bot) == 1:
                log.info('Auto-joining channel %s in guild %s', after.channel, member.guild.id)
                state['voice_client'] = await after.channel.connect()
                vc = state['voice_client']

        # User-join intro
        if not _INTRO_ON_USER_JOIN:
            return
        if vc is None or not vc.is_connected() or vc.channel != after.channel:
            return
        if vc.is_playing() or vc.is_paused():
            return
        intro = get_user_intro(member.guild.id, member.id)
        if not intro:
            return
        log.info('Playing user-join intro for %s in guild %s', member, member.guild.id)
        vc.play(discord.FFmpegPCMAudio(str(intro), **FFMPEG_OPTIONS))


async def setup(bot):
    await bot.add_cog(IntrosCog(bot))
