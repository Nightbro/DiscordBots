import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from utils.config import EMOJI_YES, EMOJI_NO
from utils.reactions import ReactionHandler


def _make_reaction(emoji: str, message_id: int) -> MagicMock:
    r = MagicMock(spec=discord.Reaction)
    r.emoji = emoji
    r.message = MagicMock()
    r.message.id = message_id
    r.__str__ = lambda self: self.emoji
    return r


async def test_confirm_yes(ctx):
    msg = MagicMock()
    msg.id = 42
    msg.add_reaction = AsyncMock()
    msg.delete = AsyncMock()
    ctx.send = AsyncMock(return_value=msg)

    reaction = _make_reaction(EMOJI_YES, 42)
    ctx.bot.wait_for = AsyncMock(return_value=(reaction, ctx.author))

    result = await ReactionHandler.confirm(ctx, 'Join?')
    assert result is True


async def test_confirm_no(ctx):
    msg = MagicMock()
    msg.id = 42
    msg.add_reaction = AsyncMock()
    msg.delete = AsyncMock()
    ctx.send = AsyncMock(return_value=msg)

    reaction = _make_reaction(EMOJI_NO, 42)
    ctx.bot.wait_for = AsyncMock(return_value=(reaction, ctx.author))

    result = await ReactionHandler.confirm(ctx, 'Join?')
    assert result is False


async def test_confirm_timeout(ctx):
    msg = MagicMock()
    msg.id = 42
    msg.add_reaction = AsyncMock()
    msg.delete = AsyncMock()
    ctx.send = AsyncMock(return_value=msg)
    ctx.bot.wait_for = AsyncMock(side_effect=asyncio.TimeoutError)

    result = await ReactionHandler.confirm(ctx, 'Join?', timeout=0.01)
    assert result is False


async def test_confirm_adds_both_reactions(ctx):
    msg = MagicMock()
    msg.id = 1
    msg.add_reaction = AsyncMock()
    msg.delete = AsyncMock()
    ctx.send = AsyncMock(return_value=msg)
    ctx.bot.wait_for = AsyncMock(side_effect=asyncio.TimeoutError)

    await ReactionHandler.confirm(ctx, 'ok?', timeout=0.01)

    added = [call.args[0] for call in msg.add_reaction.await_args_list]
    assert EMOJI_YES in added
    assert EMOJI_NO in added


async def test_confirm_deletes_message_on_yes(ctx):
    msg = MagicMock()
    msg.id = 1
    msg.add_reaction = AsyncMock()
    msg.delete = AsyncMock()
    ctx.send = AsyncMock(return_value=msg)
    reaction = _make_reaction(EMOJI_YES, 1)
    ctx.bot.wait_for = AsyncMock(return_value=(reaction, ctx.author))

    await ReactionHandler.confirm(ctx, 'ok?')
    msg.delete.assert_awaited_once()


async def test_panel_calls_callback(ctx):
    msg = MagicMock()
    msg.id = 99
    msg.add_reaction = AsyncMock()
    msg.remove_reaction = AsyncMock()
    msg.clear_reactions = AsyncMock()
    ctx.send = AsyncMock(return_value=msg)

    called_with = []

    async def callback(user):
        called_with.append(user)

    reaction = _make_reaction('🔥', 99)
    user = MagicMock()
    user.bot = False

    # First call returns a reaction, second raises TimeoutError to end loop
    ctx.bot.wait_for = AsyncMock(
        side_effect=[(reaction, user), asyncio.TimeoutError]
    )

    import discord as _discord
    embed = _discord.Embed(title='Panel')
    await ReactionHandler.panel(ctx, {'🔥': callback}, embed, timeout=5.0)

    assert called_with == [user]


async def test_panel_clears_reactions_on_timeout(ctx):
    msg = MagicMock()
    msg.id = 1
    msg.add_reaction = AsyncMock()
    msg.clear_reactions = AsyncMock()
    ctx.send = AsyncMock(return_value=msg)
    ctx.bot.wait_for = AsyncMock(side_effect=asyncio.TimeoutError)

    import discord as _discord
    embed = _discord.Embed(title='Panel')
    await ReactionHandler.panel(ctx, {'🔥': AsyncMock()}, embed, timeout=0.01)

    msg.clear_reactions.assert_awaited_once()
