from __future__ import annotations

import logging

import discord
from discord.ext import commands

from utils.config import PREFIX
from utils.message import MessageWriter

log = logging.getLogger(__name__)

# Words that get the invite link back when DM'd to the bot. A leading command
# prefix is stripped first, so "!join" works the same as "join".
_TRIGGERS = {'join', 'invite', 'add'}


def is_invite_request(content: str) -> bool:
    """True if a DM body is asking for the invite link."""
    return content.strip().lower().lstrip(PREFIX).strip() in _TRIGGERS


class InviteCog(commands.Cog, name='Invite'):
    """Answers "join" in a DM with the server-invite URL."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # DMs only — in a guild the bot is already added.
        if message.author.bot or message.guild is not None:
            return
        if not is_invite_request(message.content):
            return
        log.info('Invite link requested by %s', message.author)
        await message.channel.send(embed=MessageWriter.invite())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InviteCog(bot))
