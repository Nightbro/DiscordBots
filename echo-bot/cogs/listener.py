import discord
from discord.ext import commands

from utils.i18n import t


class ListenerCog(commands.Cog, name='Listener'):
    """Voice receive placeholder — future STT integration point."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name='listen', description='Voice listening (not yet implemented)')
    async def listen(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        await ctx.send(t('listener.not_implemented', guild_id))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ListenerCog(bot))
