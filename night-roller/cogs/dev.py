from __future__ import annotations

import sys

from discord.ext import commands

from utils.config import BOT_NAME, VERSION
from utils.message import MessageWriter


class DevCog(commands.Cog, name='Dev'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name='version')
    async def version(self, ctx: commands.Context) -> None:
        """Show the running bot version."""
        await ctx.send(embed=MessageWriter.info(f'{BOT_NAME} version', VERSION))

    @commands.hybrid_command(name='ping')
    async def ping(self, ctx: commands.Context) -> None:
        """Show gateway latency."""
        latency_ms = round(self.bot.latency * 1000)
        await ctx.send(embed=MessageWriter.info('Pong', f'{latency_ms} ms'))

    @commands.command(name='restart')
    @commands.is_owner()
    async def restart(self, ctx: commands.Context) -> None:
        """Owner only — exit so systemd restarts the process."""
        await ctx.send(embed=MessageWriter.success('Restarting', 'Back in a moment.'))
        await self.bot.close()
        sys.exit(0)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DevCog(bot))
