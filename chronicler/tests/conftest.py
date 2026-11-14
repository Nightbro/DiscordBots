import random
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import utils.config


@pytest.fixture(autouse=True)
def isolated_guild_config(tmp_path, monkeypatch):
    """Point the guild config store at a temp file for every test.

    GuildConfig reads GUILD_CONFIG_FILE at construction time, so patching the
    module attribute is enough — no test ever writes to the real data/ dir.
    """
    monkeypatch.setattr(utils.config, 'GUILD_CONFIG_FILE', tmp_path / 'guild_config.json')
    yield


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
def wod_guild(guild_id: int):
    """Configure the test guild for World of Darkness."""
    from utils.guild_config import set_system
    set_system(guild_id, 'wod')
    return guild_id


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


@pytest.fixture
def dm_message() -> MagicMock:
    """A DM to the bot: message.guild is None."""
    msg = MagicMock(spec=discord.Message)
    msg.content = 'join'
    msg.guild = None
    msg.author = MagicMock(spec=discord.User)
    msg.author.bot = False
    msg.author.id = 555555555
    msg.author.display_name = 'TestUser'
    msg.channel = MagicMock(spec=discord.DMChannel)
    msg.channel.send = AsyncMock()
    return msg


@pytest.fixture
def guild_message(dm_message: MagicMock) -> MagicMock:
    """The same message, but sent in a server channel."""
    dm_message.guild = MagicMock(spec=discord.Guild)
    dm_message.guild.id = 123456789
    return dm_message
