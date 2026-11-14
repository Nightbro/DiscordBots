"""Rendering a RollResult as text.

This sits between the engine (utils/dice.py — data and scoring, no strings for
humans) and the embed builder (utils/message.py — Discord objects). It emits
Discord-flavoured markdown but imports no Discord types, so it is as testable
as the engine itself.
"""

from __future__ import annotations

from utils.dice import RollResult


def _join(result: RollResult, chunks: list[str]) -> str:
    """Join per-group chunks with their signs, then append the modifier."""
    parts: list[str] = []
    for i, (group, chunk) in enumerate(zip(result.groups, chunks)):
        if i == 0:
            parts.append(f'-{chunk}' if group.negative else chunk)
        else:
            parts.append(f'{"-" if group.negative else "+"} {chunk}')
    if result.modifier:
        sign = '-' if result.modifier < 0 else '+'
        if not parts:
            parts.append(f'{result.modifier}')
        else:
            parts.append(f'{sign} {abs(result.modifier)}')
    return ' '.join(parts) if parts else '0'


def _face(result: RollResult, face: int) -> str:
    """Render one die face, marking hits and cancelling 1s when counting."""
    if not result.counts_successes:
        return str(face)
    if face >= result.target:  # type: ignore[operator]
        return f'**{face}**'
    if result.subtract_ones and face == 1:
        return f'__{face}__'
    return str(face)


def breakdown(result: RollResult) -> str:
    """Every die face, e.g. ``[4, 6] + 3``.

    When counting successes, hits are bold and cancelling 1s underlined.
    """
    chunks = []
    for group in result.groups:
        faces = ', '.join(_face(result, r) for r in group.rolls)
        if group.dropped:
            faces += ''.join(f', ~~{d}~~' for d in group.dropped)
        chunks.append(f'[{faces}]')
    return _join(result, chunks)


def compact_breakdown(result: RollResult) -> str:
    """Per-group subtotals instead of every face, e.g. ``2d6(10) + 3``.

    Used when a roll has too many dice to print individually — Discord caps an
    embed description at 4096 characters.
    """
    return _join(result, [f'{g.notation}({sum(g.rolls)})' for g in result.groups])


def notation(result: RollResult) -> str:
    """The signed dice notation, e.g. ``2d6 - 1d4``."""
    parts = []
    for i, group in enumerate(result.groups):
        if i == 0:
            parts.append(f'-{group.notation}' if group.negative else group.notation)
        else:
            parts.append(f'{"-" if group.negative else "+"} {group.notation}')
    return ' '.join(parts)


def wrap(detail: str) -> str:
    """Wrap a breakdown in a code span — but only when it carries no markup.

    Discord renders nothing inside a code span, so a breakdown containing bold
    hits, underlined 1s, or struck-through dropped dice has to go out as plain
    text or the readers see literal ** and ~~.
    """
    if any(marker in detail for marker in ('**', '__', '~~')):
        return detail
    return f'`{detail}`'
