import discord
from discord.ext import commands


class MusicCog(commands.Cog, name='Music'):
    """Playback: YouTube, Suno, search, queue, playlists."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
