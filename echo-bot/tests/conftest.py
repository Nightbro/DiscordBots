import pytest
import discord
from unittest.mock import AsyncMock, MagicMock

from utils.guild_state import GuildState, Track


@pytest.fixture
def guild_id() -> int:
    return 123456789


@pytest.fixture
def guild_state() -> GuildState:
    return GuildState()


@pytest.fixture
def voice_client() -> MagicMock:
    vc = MagicMock(spec=discord.VoiceClient)
    vc.is_playing.return_value = False
    vc.is_paused.return_value = False
    return vc


@pytest.fixture
def voice_channel() -> MagicMock:
    ch = MagicMock(spec=discord.VoiceChannel)
    ch.id = 111111111
    ch.name = 'General'
    return ch


@pytest.fixture
def mock_bot(guild_id: int, guild_state: GuildState) -> MagicMock:
    bot = MagicMock()
    bot.get_guild_state = MagicMock(return_value=guild_state)
    bot.is_owner = AsyncMock(return_value=True)
    bot.user = MagicMock()
    bot.user.id = 987654321
    bot.user.__str__ = lambda self: 'Echo#0001'
    bot.voice_clients = []
    bot.guilds = []
    bot.cogs = {}
    bot.extensions = {}
    return bot


@pytest.fixture
def ctx(mock_bot: MagicMock, voice_channel: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.bot = mock_bot
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 555555555
    ctx.author.display_name = 'TestUser'
    ctx.author.voice = MagicMock()
    ctx.author.voice.channel = voice_channel
    ctx.send = AsyncMock()
    ctx.reply = AsyncMock()
    return ctx


@pytest.fixture
def ctx_no_voice(ctx: MagicMock) -> MagicMock:
    ctx.author.voice = None
    return ctx


@pytest.fixture
def sample_track() -> Track:
    return Track(
        title='Test Track',
        url='https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        duration=212,
    )
