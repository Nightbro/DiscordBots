from __future__ import annotations

import logging
import re

from discord.ext import commands

from utils.config import DEFAULT_EXPRESSION
from utils.dice import DiceError, roll
from utils.message import MessageWriter

log = logging.getLogger(__name__)

_ADVANTAGE = {'adv', 'advantage', 'a'}
_DISADVANTAGE = {'dis', 'disadvantage', 'disadv', 'd'}

# A token that is part of the dice expression rather than the trailing reason.
_EXPR_TOKEN_RE = re.compile(r'^[+-]?[\dd+-]+$', re.IGNORECASE)
_FIRST_GROUP_RE = re.compile(r'(\d*)d(\d+)', re.IGNORECASE)


def split_input(text: str) -> tuple[str | None, str, str]:
    """Split raw command input into (keep_mode, expression, reason).

    ``adv 1d20+5 to hit`` → ``('high', '1d20+5', 'to hit')``
    ``2d6+3 sneak attack`` → ``(None, '2d6+3', 'sneak attack')``
    """
    tokens = text.split()
    keep: str | None = None

    if tokens and tokens[0].lower() in _ADVANTAGE:
        keep = 'high'
        tokens.pop(0)
    elif tokens and tokens[0].lower() in _DISADVANTAGE:
        keep = 'low'
        tokens.pop(0)

    expr_parts: list[str] = []
    while tokens and _EXPR_TOKEN_RE.match(tokens[0]):
        expr_parts.append(tokens.pop(0))

    return keep, ''.join(expr_parts), ' '.join(tokens)


def advantage_expression(expression: str) -> str:
    """Double the first dice group so advantage/disadvantage has two dice to pick from."""
    expr = expression.replace(' ', '')
    match = _FIRST_GROUP_RE.search(expr)
    if not match:
        # Bare modifier (or nothing at all) — advantage implies a d20 check.
        if not expr:
            return '2d20'
        return f'2d20{expr}' if expr[0] in '+-' else f'2d20+{expr}'
    count = int(match.group(1) or 1)
    return f'{expr[:match.start()]}{count * 2}d{match.group(2)}{expr[match.end():]}'


class RollCog(commands.Cog, name='Roll'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name='roll', aliases=['r'])
    async def roll_cmd(self, ctx: commands.Context, *, args: str = '') -> None:
        """Roll dice. Examples: !roll · !roll 2d6+3 · !roll adv +5 to hit"""
        keep, expression, reason = split_input(args)

        if not expression:
            expression = DEFAULT_EXPRESSION
        if keep:
            expression = advantage_expression(expression)

        try:
            result = roll(expression, keep=keep)
        except DiceError as exc:
            await ctx.send(embed=MessageWriter.error('Bad roll', str(exc)))
            return

        log.info('%s rolled %s → %s', ctx.author, expression, result.total)
        await ctx.send(
            embed=MessageWriter.roll_card(result, ctx.author.display_name, reason=reason)
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RollCog(bot))
