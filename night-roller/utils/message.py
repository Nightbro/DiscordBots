from __future__ import annotations

import discord

from utils.config import BOT_NAME, COLOR, EMOJI_CRIT, EMOJI_DICE, EMOJI_FAIL, SHOW_ROLLS
from utils.dice import RollResult

_GREEN = 0x57F287
_RED = 0xED4245


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
        notation = ' + '.join(g.notation for g in result.groups) or 'flat'
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
            lines.append(f'`{result.breakdown()}`')
        if reason:
            lines.append(f'*{reason}*')
        e.description = '\n'.join(lines)
        return e
