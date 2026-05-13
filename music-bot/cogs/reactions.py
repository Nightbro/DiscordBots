import logging

import discord
from discord.ext import commands

from utils.reaction_config import get_watches, add_watch, remove_watch

log = logging.getLogger('music-bot.reactions')

_DEFAULT_RESPONSE = '{user} reacted with {emoji}'


class ReactionsCog(commands.Cog, name='Reactions'):
    def __init__(self, bot):
        self.bot = bot

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.group(name='react', invoke_without_command=True)
    async def react_group(self, ctx: commands.Context):
        await ctx.send(
            '**Reaction commands:**\n'
            '`!react add <msg_id> <emoji>` — add a reaction to a message\n'
            '`!react count <msg_id> [emoji]` — count reactions on a message\n'
            '`!react remove <msg_id> <emoji> [@user]` — remove a reaction\n'
            '`!react watch <msg_id> <emoji> [response]` — trigger when someone reacts\n'
            '`!react unwatch <msg_id> <emoji>` — remove a trigger\n'
            '`!react watches` — list all active triggers\n'
            '\n*`{user}` and `{emoji}` are available as placeholders in watch responses.*'
        )

    @react_group.command(name='add')
    async def react_add(self, ctx: commands.Context, message_id: int, emoji: str):
        """React to a message with an emoji."""
        try:
            message = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.send(f'Message `{message_id}` not found in this channel.')
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException as e:
            return await ctx.send(f'Could not add reaction: `{e}`')
        log.info('Added reaction %s to message %s in guild %s', emoji, message_id, ctx.guild.id)
        await ctx.send(f'Added {emoji} to message `{message_id}`.')

    @react_group.command(name='count')
    async def react_count(self, ctx: commands.Context, message_id: int, emoji: str = None):
        """Count reactions on a message, optionally filtered to one emoji."""
        try:
            message = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.send(f'Message `{message_id}` not found in this channel.')

        if emoji:
            reaction = discord.utils.get(message.reactions, emoji=emoji)
            if reaction is None:
                return await ctx.send(f'No {emoji} reactions on that message.')
            await ctx.send(f'{emoji} × **{reaction.count}**')
        else:
            if not message.reactions:
                return await ctx.send('No reactions on that message.')
            lines = [f'{r.emoji} × **{r.count}**' for r in message.reactions]
            await ctx.send(f'**Reactions on `{message_id}`:**\n' + '\n'.join(lines))

    @react_group.command(name='remove')
    async def react_remove(
        self,
        ctx: commands.Context,
        message_id: int,
        emoji: str,
        member: discord.Member = None,
    ):
        """Remove a reaction from a message. Removes the bot's own if no @user given."""
        try:
            message = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.send(f'Message `{message_id}` not found in this channel.')

        target = member or ctx.me
        try:
            await message.remove_reaction(emoji, target)
        except discord.Forbidden:
            return await ctx.send(
                "I don't have permission to remove that reaction (need **Manage Messages**)."
            )
        except discord.HTTPException as e:
            return await ctx.send(f'Could not remove reaction: `{e}`')

        who = f'**{member.display_name}**' if member else 'my own'
        log.info('Removed %s reaction on msg %s (%s) in guild %s',
                 emoji, message_id, target, ctx.guild.id)
        await ctx.send(f'Removed {emoji} ({who} reaction) from `{message_id}`.')

    @react_group.command(name='watch')
    async def react_watch(
        self,
        ctx: commands.Context,
        message_id: int,
        emoji: str,
        *,
        response: str = None,
    ):
        """Trigger a message when someone reacts with emoji to a message.

        Use {user} and {emoji} as placeholders in the response.
        Defaults to: '{user} reacted with {emoji}'
        """
        add_watch(ctx.guild.id, message_id, emoji, ctx.channel.id, response)
        resp_note = f'`{response}`' if response else f'`{_DEFAULT_RESPONSE}`'
        log.info('Watch added — guild %s msg %s emoji %s', ctx.guild.id, message_id, emoji)
        await ctx.send(f'Watching {emoji} on `{message_id}` → {resp_note}.')

    @react_group.command(name='unwatch')
    async def react_unwatch(self, ctx: commands.Context, message_id: int, emoji: str):
        """Remove a reaction trigger."""
        if remove_watch(ctx.guild.id, message_id, emoji):
            log.info('Watch removed — guild %s msg %s emoji %s', ctx.guild.id, message_id, emoji)
            await ctx.send(f'No longer watching {emoji} on `{message_id}`.')
        else:
            await ctx.send(f'No watch found for {emoji} on `{message_id}`.')

    @react_group.command(name='watches')
    async def react_watches(self, ctx: commands.Context):
        """List all active reaction triggers for this server."""
        watches = get_watches(ctx.guild.id)
        if not watches:
            return await ctx.send('No reaction watches configured.')
        lines = []
        for key, entry in watches.items():
            msg_id, emoji = key.split(':', 1)
            resp = entry.get('response', _DEFAULT_RESPONSE)
            lines.append(f'{emoji} on `{msg_id}` → `{resp}`')
        await ctx.send(f'**Reaction watches ({len(lines)}):**\n' + '\n'.join(lines))

    # ── Listener ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot:
            return
        guild = reaction.message.guild
        if guild is None:
            return

        emoji_str = str(reaction.emoji)
        watches   = get_watches(guild.id)
        watch     = watches.get(f'{reaction.message.id}:{emoji_str}')
        if not watch:
            return

        channel = guild.get_channel(watch['channel_id']) or reaction.message.channel
        response = watch.get('response', _DEFAULT_RESPONSE)
        text = response.format(user=user.mention, emoji=emoji_str)
        log.info('Reaction trigger fired — guild %s msg %s emoji %s by %s',
                 guild.id, reaction.message.id, emoji_str, user)
        await channel.send(text)


async def setup(bot):
    await bot.add_cog(ReactionsCog(bot))
