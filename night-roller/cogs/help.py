from __future__ import annotations

from discord.ext import commands

from utils.config import BOT_NAME, PREFIX
from utils.guild_config import get_all_settings
from utils.message import MessageWriter

_HELP_BODY = """
**Rolling**
`{p}roll` — roll `1d{die}`
`{p}roll 5` — roll `5d{die}` (this server's default die)
`{p}roll 2d6+3` — any number of dice, plus or minus a modifier
`{p}roll d20+2d4+1` — combine groups
`{p}roll adv +5` — advantage (rolls two d20, keeps the highest)
`{p}roll dis +5` — disadvantage (keeps the lowest)
`{p}roll 2d6+3 sneak attack` — anything after the dice is shown as a label

**Counting successes**
`{p}roll 5 (6)` — roll 5 dice, count how many are 6 or higher
`{p}roll 6d10 (7)` — same, with explicit dice
{wod}

**Other**
`{p}config` — show or change this server's roll settings (Manage Server)
`{p}help` — this message
`{p}version` — running version
`{p}ping` — latency check

Alias: `{p}r`. Every command also works as a `/` slash command.
"""

_WOD_NOTE = (
    'This server uses **World of Darkness** rules: a plain `{p}roll 5` is '
    'scored at difficulty `{diff}` automatically, and each `1` cancels a success.'
)

_STANDARD_NOTE = (
    'This server sums dice by default — add `(n)` to any roll to count hits instead. '
    'Switch to World of Darkness scoring with `{p}config system wod`.'
)


class HelpCog(commands.Cog, name='Help'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name='help', aliases=['h'])
    async def help_cmd(self, ctx: commands.Context) -> None:
        """Show the command reference."""
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = get_all_settings(guild_id)
        note = _WOD_NOTE if settings['system'] == 'wod' else _STANDARD_NOTE
        body = _HELP_BODY.format(
            p=PREFIX,
            die=settings['die'],
            wod=note.format(p=PREFIX, diff=settings['difficulty']),
        ).strip()
        await ctx.send(embed=MessageWriter.info(f'{BOT_NAME} — Commands', body))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
