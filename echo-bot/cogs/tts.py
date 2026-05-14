import discord
from discord.ext import commands


class TTSCog(commands.Cog, name='TTS'):
    """edge-tts voice output, per-guild voice setting."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TTSCog(bot))
