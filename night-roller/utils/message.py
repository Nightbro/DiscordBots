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


def _success_style(result: RollResult) -> tuple[str, int, str]:
    """Emoji, color and flavour line for a success-counted roll."""
    if result.outcome == 'botch':
        return EMOJI_FAIL, _RED, '**Botch!**'
    if result.outcome == 'failure':
        return EMOJI_DICE, COLOR, '**Failure**'
    return EMOJI_CRIT, _GREEN, ''


def _success_headline(result: RollResult) -> str:
    """The big number: net successes, or the word Botch."""
    net = result.net_hits
    if result.outcome == 'botch':
        return f'Botch ({net})' if net < 0 else 'Botch'
    if net == 0:
        return '0 successes'
    return f'{net} success' if net == 1 else f'{net} successes'


def _success_maths(result: RollResult) -> str:
    """How the headline was reached, e.g. "4 hits − 1 one"."""
    hits = f'{result.hits} hit' if result.hits == 1 else f'{result.hits} hits'
    parts = [f'{hits} at {result.target}+']
    if result.subtract_ones and result.ones:
        ones = '1 one' if result.ones == 1 else f'{result.ones} ones'
        parts.append(f'− {ones}')
    return ' '.join(parts)


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
    def config_card(settings: dict, prefix: str = '!') -> discord.Embed:
        """This server's dice settings."""
        e = _embed()
        e.title = f'{EMOJI_DICE} Roll settings for this server'
        system = settings['system']
        die = settings['die']
        lines = [
            f'**System:** `{system}`',
            f'**Default die:** `d{die}` — `{prefix}roll 5` rolls `5d{die}`',
        ]
        if system == 'wod':
            ones = 'on' if settings['subtract_ones'] else 'off'
            lines.append(f'**Difficulty:** `{settings["difficulty"]}` — dice at or above this are hits')
            lines.append(f'**Subtract 1s:** `{ones}`')
        else:
            lines.append(f'**Difficulty:** `{settings["difficulty"]}` — used only when you ask for `(n)`')
        lines.append('')
        lines.append(f'Change with `{prefix}config system|die|difficulty|ones <value>`')
        e.description = '\n'.join(lines)
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

        if result.counts_successes:
            emoji, color, flavour = _success_style(result)

        e = _embed(color)
        label = f'{roller} rolls ' if roller else 'Rolled '
        notation = result.notation() or 'flat'
        if len(notation) > _MAX_TITLE_NOTATION:
            notation = f'{len(result.groups)} dice groups'
        if result.keep == 'high':
            notation += ' (advantage)'
        elif result.keep == 'low':
            notation += ' (disadvantage)'
        if result.counts_successes:
            notation += f' · difficulty {result.target}'

        e.title = f'{emoji} {label}{notation}'
        lines = []
        if flavour:
            lines.append(flavour)
        if result.counts_successes:
            lines.append(f'# {_success_headline(result)}')
            lines.append(_success_maths(result))
        else:
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
