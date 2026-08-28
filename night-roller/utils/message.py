from __future__ import annotations

import discord

from utils.config import (
    BOT_NAME,
    COLOR,
    EMOJI_CRIT,
    EMOJI_DICE,
    EMOJI_FAIL,
    INVITE_URL,
    SHOW_ROLLS,
)
from utils.dice import RollResult

_GREEN = 0x57F287
_RED = 0xED4245

# Discord's hard limits are 256 for a title and 4096 for a description, but a
# wall of numbers stops being readable long before that — collapse to summary
# form at these lengths instead. ~600 chars is roughly 150 individual dice.
_MAX_TITLE_NOTATION = 120
_MAX_BREAKDOWN = 600


def _embed(color: int = COLOR) -> discord.Embed:
    e = discord.Embed(color=color)
    e.set_footer(text=BOT_NAME)
    return e


class MessageWriter:
    """Every embed the bot sends is built here — cogs never touch discord.Embed."""

    @staticmethod
    def success(title: str, description: str = '') -> discord.Embed:
        e = _embed(_GREEN)
        e.title = f'✅ {title}'
        if description:
            e.description = description
        return e

    @staticmethod
    def error(title: str, description: str = '') -> discord.Embed:
        e = _embed(_RED)
        e.title = f'❌ {title}'
        if description:
            e.description = description
        return e

    @staticmethod
    def info(title: str, description: str = '') -> discord.Embed:
        e = _embed()
        e.title = f'ℹ️ {title}'
        if description:
            e.description = description
        return e

    @staticmethod
    def invite() -> discord.Embed:
        """Reply to a "join" DM — how to add the bot to a server."""
        e = _embed()
        e.title = f'{EMOJI_DICE} Add {BOT_NAME} to your server'
        e.description = f'To add me to your server use this url:\n\n{INVITE_URL}'
        return e

    @staticmethod
    def roll_card(result: RollResult, roller: str = '', *, reason: str = '') -> discord.Embed:
        """The result of one !roll."""
        emoji = EMOJI_DICE
        color = COLOR
        flavour = ''

        natural = result.natural
        if result.is_single_d20 and natural is not None:
            if natural == 20:
                emoji, color, flavour = EMOJI_CRIT, _GREEN, '**Natural 20!**'
            elif natural == 1:
                emoji, color, flavour = EMOJI_FAIL, _RED, '**Natural 1...**'

        e = _embed(color)
        label = f'{roller} rolls ' if roller else 'Rolled '
        notation = result.notation() or 'flat'
        if len(notation) > _MAX_TITLE_NOTATION:
            notation = f'{len(result.groups)} dice groups'
        if result.keep == 'high':
            notation += ' (advantage)'
        elif result.keep == 'low':
            notation += ' (disadvantage)'

        e.title = f'{emoji} {label}{notation}'
        lines = []
        if flavour:
            lines.append(flavour)
        lines.append(f'# {result.total}')
        if SHOW_ROLLS:
            detail = result.breakdown()
            if len(detail) > _MAX_BREAKDOWN:
                # Too many dice to list — fall back to per-group subtotals,
                # and drop the breakdown entirely if even that is too long.
                detail = result.compact_breakdown()
                if len(detail) > _MAX_BREAKDOWN:
                    detail = ''
            if detail:
                lines.append(f'`{detail}`')
        if reason:
            lines.append(f'*{reason}*')
        e.description = '\n'.join(lines)
        return e
