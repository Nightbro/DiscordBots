import discord
from discord.ext import commands


class IntrosCog(commands.Cog, name='Intros'):
    """Per-user/bot join sounds with schedule support."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(IntrosCog(bot))
