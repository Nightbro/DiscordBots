import discord
from discord.ext import commands


class ListenerCog(commands.Cog, name='Listener'):
    """Voice receive placeholder — future STT integration point."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name='listen', description='Voice listening (not yet implemented)')
    async def listen(self, ctx: commands.Context) -> None:
        await ctx.send('Voice listening is not yet implemented.')


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ListenerCog(bot))
