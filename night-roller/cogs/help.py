from __future__ import annotations

from discord.ext import commands

from utils.config import BOT_NAME, DEFAULT_EXPRESSION, PREFIX
from utils.message import MessageWriter

_HELP_BODY = """
**Rolling**
`{p}roll` — roll `{default}`
`{p}roll 2d6+3` — any number of dice, plus or minus a modifier
`{p}roll d20+2d4+1` — combine groups
`{p}roll adv +5` — advantage (rolls two d20, keeps the highest)
`{p}roll dis +5` — disadvantage (keeps the lowest)
`{p}roll 2d6+3 sneak attack` — anything after the dice is shown as a label

Alias: `{p}r`. Every command also works as a `/` slash command.

**Other**
`{p}help` — this message
`{p}version` — running version
`{p}ping` — latency check
"""


class HelpCog(commands.Cog, name='Help'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name='help', aliases=['h'])
    async def help_cmd(self, ctx: commands.Context) -> None:
        """Show the command reference."""
        body = _HELP_BODY.format(p=PREFIX, default=DEFAULT_EXPRESSION).strip()
        await ctx.send(embed=MessageWriter.info(f'{BOT_NAME} — Commands', body))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
