"""Dice expression parsing, rolling and scoring.

Grammar (whitespace is ignored, case-insensitive):

    expression := term (('+' | '-') term)*
    term       := [count] 'd' sides | constant

Examples: ``d20``  ``2d6+3``  ``4d6 - 1``  ``d20+2d4+1``

This module holds data and scoring only. It has no Discord types *and* no
rendering — turning a result into text for a human lives in utils/format.py,
so the engine can be read and tested without any presentation in the way.
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
    target: int | None = None       # count dice >= this instead of summing
    subtract_ones: bool = False     # each 1 cancels a success (WoD botch rule)

    # --- Success counting --------------------------------------------------

    @property
    def counts_successes(self) -> bool:
        return self.target is not None

    @property
    def faces(self) -> list[int]:
        """Every kept die face across all groups."""
        return [face for group in self.groups for face in group.rolls]

    @property
    def hits(self) -> int:
        """Dice that met or beat the target."""
        if self.target is None:
            return 0
        return sum(1 for face in self.faces if face >= self.target)

    @property
    def ones(self) -> int:
        """Dice that came up 1 — only counted when the botch rule is on."""
        if not self.subtract_ones:
            return 0
        return sum(1 for face in self.faces if face == 1)

    @property
    def net_hits(self) -> int:
        """Successes after 1s cancel them out. Can go negative — that's a botch."""
        return self.hits - self.ones

    @property
    def outcome(self) -> str:
        """'success' | 'failure' | 'botch' — only meaningful when counting.

        A botch is any roll where 1s came up and no successes survived them —
        including successes cancelled exactly down to zero. A plain failure is
        rolling nothing good with no 1s either.
        """
        if self.net_hits > 0:
            return 'success'
        if self.ones > 0:
            return 'botch'
        return 'failure'

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


def roll(
    expression: str,
    *,
    keep: str | None = None,
    target: int | None = None,
    subtract_ones: bool = False,
    rng: random.Random | None = None,
) -> RollResult:
    """Parse and roll an expression.

    keep: ``'high'`` or ``'low'`` keeps the single best/worst die of the first
    group and drops the rest — this is how advantage and disadvantage work.

    target: when given, the result is scored as successes (dice >= target)
    instead of a sum. ``subtract_ones`` additionally cancels one success per 1
    rolled — the World of Darkness botch rule.
    """
    if keep not in (None, 'high', 'low'):
        raise DiceError(f'Unknown keep mode: {keep!r}')
    if target is not None and target < 1:
        raise DiceError('Difficulty must be at least 1.')

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
        target=target,
        subtract_ones=subtract_ones,
    )
