"""Dice expression parsing and rolling.

Grammar (whitespace is ignored, case-insensitive):

    expression := term (('+' | '-') term)*
    term       := [count] 'd' sides | constant

Examples: ``d20``  ``2d6+3``  ``4d6 - 1``  ``d20+2d4+1``

The module is deliberately free of Discord types so it can be unit-tested
directly; the cog is responsible for all presentation.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from utils.config import MAX_DICE, MAX_GROUPS, MAX_SIDES

# One token: either NdM (count optional) or a bare number, each with an
# optional leading sign.
_TOKEN_RE = re.compile(r'([+-]?)\s*(?:(\d*)d(\d+)|(\d+))', re.IGNORECASE)


class DiceError(ValueError):
    """Raised for anything the user can fix by retyping the expression."""


@dataclass
class DiceGroup:
    """One ``NdM`` term and the individual faces it rolled."""

    count: int
    sides: int
    rolls: list[int] = field(default_factory=list)
    dropped: list[int] = field(default_factory=list)
    negative: bool = False

    @property
    def notation(self) -> str:
        return f'{self.count}d{self.sides}'

    @property
    def subtotal(self) -> int:
        total = sum(self.rolls)
        return -total if self.negative else total


@dataclass
class RollResult:
    expression: str
    groups: list[DiceGroup]
    modifier: int
    total: int
    keep: str | None = None

    @property
    def is_single_d20(self) -> bool:
        """True for a lone d20 (with or without a flat modifier) — the
        natural-20 / natural-1 case worth calling out."""
        return len(self.groups) == 1 and self.groups[0].sides == 20 and len(self.groups[0].rolls) == 1

    @property
    def natural(self) -> int | None:
        """The raw die face for a single-die roll, else None."""
        if len(self.groups) == 1 and len(self.groups[0].rolls) == 1:
            return self.groups[0].rolls[0]
        return None

    def _join(self, chunks: list[str]) -> str:
        """Join per-group chunks with their signs, then append the modifier."""
        parts: list[str] = []
        for i, (group, chunk) in enumerate(zip(self.groups, chunks)):
            if i == 0:
                parts.append(f'-{chunk}' if group.negative else chunk)
            else:
                parts.append(f'{"-" if group.negative else "+"} {chunk}')
        if self.modifier:
            sign = '-' if self.modifier < 0 else '+'
            if not parts:
                parts.append(f'{self.modifier}')
            else:
                parts.append(f'{sign} {abs(self.modifier)}')
        return ' '.join(parts) if parts else '0'

    def breakdown(self) -> str:
        """Every die face, e.g. ``[4, 6] + 3``."""
        chunks = []
        for group in self.groups:
            faces = ', '.join(str(r) for r in group.rolls)
            if group.dropped:
                faces += ''.join(f', ~~{d}~~' for d in group.dropped)
            chunks.append(f'[{faces}]')
        return self._join(chunks)

    def compact_breakdown(self) -> str:
        """Per-group subtotals instead of every face, e.g. ``2d6(10) + 3``.

        Used when a roll has too many dice to print individually — Discord
        caps an embed description at 4096 characters.
        """
        return self._join([f'{g.notation}({sum(g.rolls)})' for g in self.groups])

    def notation(self) -> str:
        """The signed dice notation, e.g. ``2d6 - 1d4``."""
        parts = []
        for i, group in enumerate(self.groups):
            if i == 0:
                parts.append(f'-{group.notation}' if group.negative else group.notation)
            else:
                parts.append(f'{"-" if group.negative else "+"} {group.notation}')
        return ' '.join(parts)


def parse(expression: str) -> tuple[list[DiceGroup], int]:
    """Split an expression into unrolled dice groups and a flat modifier.

    Raises DiceError on anything unparseable or over the configured limits.
    """
    expr = expression.strip().lower().replace(' ', '')
    if not expr:
        raise DiceError('Empty expression.')
    if not re.fullmatch(r'[+-]?[\dd+-]*', expr):
        raise DiceError(f'`{expression}` contains characters I do not understand.')

    groups: list[DiceGroup] = []
    modifier = 0
    consumed = 0

    for index, match in enumerate(_TOKEN_RE.finditer(expr)):
        if match.start() != consumed:
            raise DiceError(f'`{expression}` is not a valid dice expression.')
        consumed = match.end()

        sign, count_txt, sides_txt, const_txt = match.groups()
        # Terms after the first must be joined by + or - — catches "1d6d4".
        if index > 0 and not sign:
            raise DiceError(f'`{expression}` is missing a + or - between terms.')
        negative = sign == '-'

        if const_txt is not None:
            value = int(const_txt)
            modifier += -value if negative else value
            continue

        count = int(count_txt) if count_txt else 1
        sides = int(sides_txt)

        if count < 1:
            raise DiceError('You need to roll at least one die.')
        if count > MAX_DICE:
            raise DiceError(f'Too many dice — the limit is {MAX_DICE} per group.')
        if sides < 2:
            raise DiceError('A die needs at least 2 sides.')
        if sides > MAX_SIDES:
            raise DiceError(f'Die is too big — the limit is d{MAX_SIDES}.')

        groups.append(DiceGroup(count=count, sides=sides, negative=negative))
        if len(groups) > MAX_GROUPS:
            raise DiceError(f'Too many dice groups — the limit is {MAX_GROUPS}.')

    if consumed != len(expr):
        raise DiceError(f'`{expression}` is not a valid dice expression.')
    if not groups and modifier == 0 and expr not in ('0', '+0', '-0'):
        raise DiceError(f'`{expression}` has no dice to roll.')

    return groups, modifier


def roll(expression: str, *, keep: str | None = None, rng: random.Random | None = None) -> RollResult:
    """Parse and roll an expression.

    keep: ``'high'`` or ``'low'`` keeps the single best/worst die of the first
    group and drops the rest — this is how advantage and disadvantage work.
    """
    if keep not in (None, 'high', 'low'):
        raise DiceError(f'Unknown keep mode: {keep!r}')

    generator = rng or random
    groups, modifier = parse(expression)

    for index, group in enumerate(groups):
        faces = [generator.randint(1, group.sides) for _ in range(group.count)]
        if keep and index == 0 and len(faces) > 1:
            best = max(faces) if keep == 'high' else min(faces)
            faces.remove(best)
            group.dropped = faces
            group.rolls = [best]
        else:
            group.rolls = faces

    total = sum(g.subtotal for g in groups) + modifier
    return RollResult(
        expression=expression.strip(),
        groups=groups,
        modifier=modifier,
        total=total,
        keep=keep,
    )
