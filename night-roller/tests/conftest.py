import random
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest


@pytest.fixture
def guild_id() -> int:
    return 123456789


@pytest.fixture
def mock_bot(guild_id: int) -> MagicMock:
    bot = MagicMock()
    bot.is_owner = AsyncMock(return_value=True)
    bot.user = MagicMock()
    bot.user.id = 987654321
    bot.latency = 0.042
    bot.close = AsyncMock()
    return bot


@pytest.fixture
def ctx(mock_bot: MagicMock, guild_id: int) -> MagicMock:
    ctx = MagicMock()
    ctx.bot = mock_bot
    ctx.guild = MagicMock()
    ctx.guild.id = guild_id
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 555555555
    ctx.author.display_name = 'TestUser'
    ctx.send = AsyncMock()
    ctx.reply = AsyncMock()
    return ctx


@pytest.fixture
def seeded_rng() -> random.Random:
    """Deterministic RNG so roll results are reproducible in tests."""
    return random.Random(1234)


def sent_embed(ctx: MagicMock):
    """The embed from the most recent ctx.send call."""
    return ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
