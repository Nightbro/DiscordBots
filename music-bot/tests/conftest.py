"""Shared fixtures for all test modules."""
import asyncio
import os
from collections import deque
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure env vars are present before any utils.config import
os.environ.setdefault("DISCORD_TOKEN", "fake_token_for_tests")
os.environ.setdefault("INTRO_ON_BOT_JOIN", "true")
os.environ.setdefault("INTRO_ON_USER_JOIN", "true")


# ---------------------------------------------------------------------------
# Bot / guild state
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.guild_states = {}
    bot.loop = asyncio.get_event_loop()
    return bot


@pytest.fixture
def guild_id():
    return 111222333


@pytest.fixture
def voice_client():
    vc = MagicMock()
    vc.is_connected.return_value = True
    vc.is_playing.return_value = False
    vc.is_paused.return_value = False
    vc.disconnect = AsyncMock()
    vc.move_to = AsyncMock()
    vc.stop = MagicMock()
    vc.pause = MagicMock()
    vc.resume = MagicMock()
    vc.play = MagicMock()
    vc.channel = MagicMock()
    return vc


# ---------------------------------------------------------------------------
# Discord context
# ---------------------------------------------------------------------------

@pytest.fixture
def voice_channel():
    ch = MagicMock()
    ch.name = "General"
    ch.connect = AsyncMock(return_value=MagicMock(
        is_connected=lambda: True,
        is_playing=lambda: False,
        is_paused=lambda: False,
        disconnect=AsyncMock(),
        stop=MagicMock(),
        pause=MagicMock(),
        resume=MagicMock(),
        play=MagicMock(),
        channel=ch,
    ))
    return ch


@pytest.fixture
def ctx(mock_bot, voice_channel):
    c = MagicMock()
    c.bot = mock_bot
    c.guild.id = 111222333
    c.author.voice = MagicMock()
    c.author.voice.channel = voice_channel
    c.send = AsyncMock()
    c.channel = MagicMock()
    c.message.attachments = []
    return c


@pytest.fixture
def ctx_no_voice(ctx):
    ctx.author.voice = None
    return ctx


# ---------------------------------------------------------------------------
# Sample track dicts
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_track(tmp_path):
    f = tmp_path / "track.mp3"
    f.write_bytes(b"\xff\xfb" * 100)  # minimal fake MP3 bytes
    return {
        "file": str(f),
        "title": "Test Track",
        "duration": 180,
        "webpage_url": "https://youtube.com/watch?v=test123",
        "from_cache": False,
    }


@pytest.fixture
def intro_track(tmp_path):
    f = tmp_path / "intro.mp3"
    f.write_bytes(b"\xff\xfb" * 50)
    return {
        "file": str(f),
        "title": None,
        "duration": 0,
        "_intro": True,
    }
