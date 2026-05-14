import discord
from discord.ext import commands


class SoundboardCog(commands.Cog, name='Soundboard'):
    """Reaction-based soundboard panel."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SoundboardCog(bot))
