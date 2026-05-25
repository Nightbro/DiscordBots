from unittest.mock import AsyncMock, MagicMock, patch

import discord

from utils.guild_state import GuildState
from utils.shutdown import announce_maintenance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _guild(guild_id: int, channel=None):
    g = MagicMock(spec=discord.Guild)
    g.id = guild_id
    g.get_channel = MagicMock(return_value=channel)
    return g


def _vc(connected=True, playing=False, paused=False):
    vc = MagicMock(spec=discord.VoiceClient)
    vc.is_connected.return_value = connected
    vc.is_playing.return_value = playing
    vc.is_paused.return_value = paused
    vc.stop = MagicMock()
    vc.play = MagicMock()
    return vc


def _bot(*guilds):
    b = MagicMock()
    b.guilds = list(guilds)
    return b


# ---------------------------------------------------------------------------
# Text announcement
# ---------------------------------------------------------------------------

async def test_sends_embed_to_last_text_channel():
    channel = AsyncMock()
    guild = _guild(1, channel=channel)
    state = GuildState()
    state.last_text_channel_id = 42
    state.voice_client = _vc(connected=True)  # bot must be in voice

    with patch('utils.shutdown._play_tts', new=AsyncMock()):
        await announce_maintenance(_bot(guild), {1: state}, 'Down for maintenance.')

    channel.send.assert_awaited_once()
    embed = channel.send.call_args.kwargs.get('embed') or channel.send.call_args.args[0]
    assert 'Maintenance' in embed.title
    assert 'Down for maintenance.' in embed.description


async def test_skips_all_when_not_in_voice():
    """Guild with no voice connection receives neither embed nor TTS."""
    channel = AsyncMock()
    guild = _guild(1, channel=channel)
    state = GuildState()
    state.last_text_channel_id = 42
    state.voice_client = None  # not in voice

    with patch('utils.shutdown._play_tts', new=AsyncMock()) as mock_tts:
        await announce_maintenance(_bot(guild), {1: state}, 'msg')

    channel.send.assert_not_awaited()
    mock_tts.assert_not_awaited()


async def test_skips_all_when_vc_disconnected():
    """Guild whose vc reports is_connected=False is also skipped."""
    channel = AsyncMock()
    guild = _guild(1, channel=channel)
    state = GuildState()
    state.last_text_channel_id = 42
    state.voice_client = _vc(connected=False)

    with patch('utils.shutdown._play_tts', new=AsyncMock()) as mock_tts:
        await announce_maintenance(_bot(guild), {1: state}, 'msg')

    channel.send.assert_not_awaited()
    mock_tts.assert_not_awaited()


async def test_skips_text_when_no_channel_id():
    guild = _guild(1)
    state = GuildState()
    state.last_text_channel_id = None
    state.voice_client = _vc(connected=True)  # bot must be in voice

    with patch('utils.shutdown._play_tts', new=AsyncMock()):
        await announce_maintenance(_bot(guild), {1: state}, 'msg')

    guild.get_channel.assert_not_called()


async def test_skips_text_when_channel_not_found():
    guild = _guild(1, channel=None)  # get_channel returns None
    state = GuildState()
    state.last_text_channel_id = 999
    state.voice_client = _vc(connected=True)  # bot must be in voice

    with patch('utils.shutdown._play_tts', new=AsyncMock()):
        # Should not raise
        await announce_maintenance(_bot(guild), {1: state}, 'msg')


async def test_skips_guild_with_no_state():
    guild = _guild(1)

    # No entry in guild_states — should not touch guild at all
    await announce_maintenance(_bot(guild), {}, 'msg')

    guild.get_channel.assert_not_called()


# ---------------------------------------------------------------------------
# Voice / TTS announcement
# ---------------------------------------------------------------------------

async def test_plays_tts_when_in_voice():
    guild = _guild(1)
    state = GuildState()
    vc = _vc(connected=True)
    state.voice_client = vc

    with patch('utils.shutdown._play_tts', new=AsyncMock()) as mock_tts:
        await announce_maintenance(_bot(guild), {1: state}, 'Shutting down.')

    mock_tts.assert_awaited_once_with(vc, 'Shutting down.', state.tts_voice)


async def test_skips_tts_when_voice_client_is_none():
    guild = _guild(1)
    state = GuildState()
    state.voice_client = None

    with patch('utils.shutdown._play_tts', new=AsyncMock()) as mock_tts:
        await announce_maintenance(_bot(guild), {1: state})

    mock_tts.assert_not_awaited()


async def test_skips_tts_when_vc_not_connected():
    guild = _guild(1)
    state = GuildState()
    state.voice_client = _vc(connected=False)

    with patch('utils.shutdown._play_tts', new=AsyncMock()) as mock_tts:
        await announce_maintenance(_bot(guild), {1: state})

    mock_tts.assert_not_awaited()


# ---------------------------------------------------------------------------
# Multiple guilds
# ---------------------------------------------------------------------------

async def test_announces_only_to_guilds_in_voice():
    """Guilds with an active voice connection get the banner; others are skipped."""
    ch1, ch2 = AsyncMock(), AsyncMock()
    guild1 = _guild(1, channel=ch1)
    guild2 = _guild(2, channel=ch2)
    state1, state2 = GuildState(), GuildState()
    state1.last_text_channel_id = 11
    state1.voice_client = _vc(connected=True)   # in voice → should announce
    state2.last_text_channel_id = 22
    state2.voice_client = None                  # not in voice → skip

    with patch('utils.shutdown._play_tts', new=AsyncMock()):
        await announce_maintenance(_bot(guild1, guild2), {1: state1, 2: state2}, 'msg')

    ch1.send.assert_awaited_once()
    ch2.send.assert_not_awaited()


async def test_continues_after_channel_send_error():
    """A send failure on one guild must not prevent announcements to others."""
    ch1 = AsyncMock(side_effect=Exception('discord error'))
    ch2 = AsyncMock()
    guild1 = _guild(1, channel=ch1)
    guild2 = _guild(2, channel=ch2)
    state1, state2 = GuildState(), GuildState()
    state1.last_text_channel_id = 11
    state1.voice_client = _vc(connected=True)
    state2.last_text_channel_id = 22
    state2.voice_client = _vc(connected=True)

    with patch('utils.shutdown._play_tts', new=AsyncMock()):
        await announce_maintenance(_bot(guild1, guild2), {1: state1, 2: state2}, 'msg')

    ch2.send.assert_awaited_once()
