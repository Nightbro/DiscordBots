from __future__ import annotations

import logging
import re

from discord.ext import commands

from utils.dice import DiceError, roll
from utils.guild_config import (
    get_die,
    get_difficulty,
    get_subtract_ones,
    is_wod,
    max_pool,
)
from utils.message import MessageWriter

log = logging.getLogger(__name__)

_ADVANTAGE = {'adv', 'advantage', 'a'}
_DISADVANTAGE = {'dis', 'disadvantage', 'disadv', 'd'}

# A token that is part of the dice expression rather than the trailing reason.
_EXPR_TOKEN_RE = re.compile(r'^[+-]?[\dd+-]+$', re.IGNORECASE)
_FIRST_GROUP_RE = re.compile(r'(\d*)d(\d+)', re.IGNORECASE)
# The difficulty in "5 (6)" — anywhere in the input, with or without a space.
_TARGET_RE = re.compile(r'\((\d+)\)')
# A pool with no die attached: "5" means "five of this server's default die".
_BARE_POOL_RE = re.compile(r'^\d+$')


def split_input(text: str) -> tuple[str | None, str, int | None, str]:
    """Split raw command input into (keep_mode, expression, target, reason).

    ``adv 1d20+5 to hit``  → ``('high', '1d20+5', None, 'to hit')``
    ``5 (6) intimidate``   → ``(None, '5', 6, 'intimidate')``
    """
    target: int | None = None
    match = _TARGET_RE.search(text)
    if match:
        target = int(match.group(1))
        text = f'{text[:match.start()]} {text[match.end():]}'

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

    return keep, ''.join(expr_parts), target, ' '.join(tokens)


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


def is_bare_pool(expression: str) -> bool:
    """True for a dice-less count like ``5`` — "five of the server's default die"."""
    return bool(_BARE_POOL_RE.match(expression.strip()))


def resolve_expression(expression: str, die: int) -> str:
    """Turn a bare pool into real dice notation. Anything else passes through."""
    expr = expression.strip()
    if not expr:
        return f'1d{die}'
    if is_bare_pool(expr):
        return f'{int(expr)}d{die}'
    return expr


class RollCog(commands.Cog, name='Roll'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name='roll', aliases=['r'])
    async def roll_cmd(self, ctx: commands.Context, *, args: str = '') -> None:
        """Roll dice. Examples: !roll · !roll 2d6+3 · !roll 5 (6) · !roll adv +5"""
        guild_id = ctx.guild.id if ctx.guild else 0
        keep, expression, target, reason = split_input(args)

        die = get_die(guild_id)
        bare = not expression.strip() or is_bare_pool(expression)

        if bare and is_bare_pool(expression) and int(expression) > max_pool():
            await ctx.send(embed=MessageWriter.error(
                'Pool too big', f'The limit is {max_pool()} dice.'
            ))
            return

        expression = resolve_expression(expression, die)
        if keep:
            expression = advantage_expression(expression)

        # In a World of Darkness server a plain pool is scored against the
        # server difficulty automatically; explicit notation like 2d6+3d8 is
        # left alone unless the user asked for a target with (n).
        subtract_ones = False
        if target is None and bare and is_wod(guild_id):
            target = get_difficulty(guild_id)
        if target is not None and is_wod(guild_id):
            subtract_ones = get_subtract_ones(guild_id)

        try:
            result = roll(expression, keep=keep, target=target, subtract_ones=subtract_ones)
        except DiceError as exc:
            await ctx.send(embed=MessageWriter.error('Bad roll', str(exc)))
            return

        log.info(
            '%s rolled %s (target=%s) → %s',
            ctx.author, expression, target,
            result.net_hits if result.counts_successes else result.total,
        )
        await ctx.send(
            embed=MessageWriter.roll_card(result, ctx.author.display_name, reason=reason)
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RollCog(bot))
