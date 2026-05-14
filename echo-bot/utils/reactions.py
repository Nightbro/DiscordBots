import asyncio
import logging
from typing import Callable, Awaitable

import discord
from discord.ext import commands

from utils.config import EMOJI_YES, EMOJI_NO, PANEL_TIMEOUT

log = logging.getLogger(__name__)


class ReactionHandler:
    @staticmethod
    async def confirm(
        ctx: commands.Context,
        prompt: str,
        timeout: float = 30.0,
    ) -> bool:
        """Send prompt, wait for ✅/❌ from ctx.author. Returns True for yes."""
        msg = await ctx.send(prompt)
        await msg.add_reaction(EMOJI_YES)
        await msg.add_reaction(EMOJI_NO)

        def check(reaction: discord.Reaction, user: discord.User) -> bool:
            return (
                user == ctx.author
                and str(reaction.emoji) in (EMOJI_YES, EMOJI_NO)
                and reaction.message.id == msg.id
            )

        try:
            reaction, _ = await ctx.bot.wait_for(
                'reaction_add', timeout=timeout, check=check
            )
            return str(reaction.emoji) == EMOJI_YES
        except asyncio.TimeoutError:
            return False
        finally:
            try:
                await msg.delete()
            except discord.HTTPException:
                pass

    @staticmethod
    async def panel(
        ctx: commands.Context,
        options: dict[str, Callable[[discord.Member], Awaitable[None]]],
        embed: discord.Embed,
        timeout: float = float(PANEL_TIMEOUT),
    ) -> None:
        """Send embed as an interactive panel. Each emoji key maps to an async callback."""
        msg = await ctx.send(embed=embed)
        for emoji in options:
            await msg.add_reaction(emoji)

        def check(reaction: discord.Reaction, user: discord.User) -> bool:
            return (
                not user.bot
                and str(reaction.emoji) in options
                and reaction.message.id == msg.id
            )

        loop = asyncio.get_event_loop()
        end_time = loop.time() + timeout

        while True:
            remaining = end_time - loop.time()
            if remaining <= 0:
                break
            try:
                reaction, user = await ctx.bot.wait_for(
                    'reaction_add', timeout=remaining, check=check
                )
                callback = options[str(reaction.emoji)]
                try:
                    await callback(user)
                except Exception:
                    log.exception('Panel callback error for emoji %s', reaction.emoji)
                try:
                    await msg.remove_reaction(reaction.emoji, user)
                except discord.HTTPException:
                    pass
            except asyncio.TimeoutError:
                break

        try:
            await msg.clear_reactions()
        except discord.HTTPException:
            pass
