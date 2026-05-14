from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.tts import TTSCog


def _cog(mock_bot) -> TTSCog:
    return TTSCog(mock_bot)


# ---------------------------------------------------------------------------
# !say
# ---------------------------------------------------------------------------

async def test_say_no_voice(mock_bot, ctx_no_voice):
    cog = _cog(mock_bot)
    await cog.say.callback(cog, ctx_no_voice, text='hello')
    embed = ctx_no_voice.send.call_args.kwargs.get('embed') or ctx_no_voice.send.call_args.args[0]
    assert '❌' in embed.title


async def test_say_synthesis_error(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.tts.VoiceStreamer') as MockStreamer:
        MockStreamer.return_value = AsyncMock()
        with patch('cogs.tts.edge_tts.Communicate') as MockComm:
            instance = AsyncMock()
            instance.save.side_effect = RuntimeError('network error')
            MockComm.return_value = instance
            await cog.say.callback(cog, ctx, text='hello')

    # Last send or edit should be an error embed
    call = ctx.send.return_value.edit.call_args
    embed = call.kwargs.get('embed') or call.args[0]
    assert '❌' in embed.title


async def test_say_success(mock_bot, ctx, tmp_path):
    cog = _cog(mock_bot)
    with patch('cogs.tts.VoiceStreamer') as MockStreamer:
        mock_streamer = AsyncMock()
        MockStreamer.return_value = mock_streamer
        with patch('cogs.tts.DOWNLOADS_DIR', tmp_path):
            with patch('cogs.tts.edge_tts.Communicate') as MockComm:
                instance = AsyncMock()
                instance.save = AsyncMock()
                MockComm.return_value = instance
                await cog.say.callback(cog, ctx, text='hello world')

    mock_streamer.interrupt.assert_awaited_once()
    track = mock_streamer.interrupt.call_args.args[0]
    assert 'TTS' in track.title
    assert track.cleanup_path is not None


# ---------------------------------------------------------------------------
# !tts voice
# ---------------------------------------------------------------------------

async def test_tts_voice_not_found(mock_bot, ctx):
    cog = _cog(mock_bot)
    voices = [{'ShortName': 'en-US-AriaNeural', 'FriendlyName': 'Aria'}]
    with patch('cogs.tts.edge_tts.list_voices', new=AsyncMock(return_value=voices)):
        await cog.tts_voice.callback(cog, ctx, name='xx-YY-FakeNeural')
    call = ctx.send.return_value.edit.call_args
    embed = call.kwargs.get('embed') or call.args[0]
    assert '❌' in embed.title


async def test_tts_voice_set_success(mock_bot, ctx):
    cog = _cog(mock_bot)
    voices = [{'ShortName': 'en-US-AriaNeural', 'FriendlyName': 'Aria'}]
    with patch('cogs.tts.edge_tts.list_voices', new=AsyncMock(return_value=voices)):
        with patch('cogs.tts.set_tts_voice') as mock_set:
            await cog.tts_voice.callback(cog, ctx, name='en-US-AriaNeural')
    mock_set.assert_called_once_with(ctx.guild.id, 'en-US-AriaNeural')
    call = ctx.send.return_value.edit.call_args
    embed = call.kwargs.get('embed') or call.args[0]
    assert '✅' in embed.title


async def test_tts_voice_fetch_error(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.tts.edge_tts.list_voices', new=AsyncMock(side_effect=RuntimeError('err'))):
        await cog.tts_voice.callback(cog, ctx, name='anything')
    call = ctx.send.return_value.edit.call_args
    embed = call.kwargs.get('embed') or call.args[0]
    assert '❌' in embed.title


# ---------------------------------------------------------------------------
# !tts voices
# ---------------------------------------------------------------------------

async def test_tts_voices_no_filter(mock_bot, ctx):
    cog = _cog(mock_bot)
    voices = [
        {'ShortName': 'en-US-AriaNeural', 'FriendlyName': 'Microsoft Aria Online', 'Locale': 'en-US'},
        {'ShortName': 'sr-Latn-RS-NicholasNeural', 'FriendlyName': 'Nicholas', 'Locale': 'sr-Latn-RS'},
    ]
    with patch('cogs.tts.edge_tts.list_voices', new=AsyncMock(return_value=voices)):
        await cog.tts_voices.callback(cog, ctx)
    call = ctx.send.return_value.edit.call_args
    embed = call.kwargs.get('embed') or call.args[0]
    assert 'AriaNeural' in embed.description


async def test_tts_voices_locale_filter(mock_bot, ctx):
    cog = _cog(mock_bot)
    voices = [
        {'ShortName': 'en-US-AriaNeural', 'FriendlyName': 'Aria', 'Locale': 'en-US'},
        {'ShortName': 'sr-Latn-RS-NicholasNeural', 'FriendlyName': 'Nicholas', 'Locale': 'sr-Latn-RS'},
    ]
    with patch('cogs.tts.edge_tts.list_voices', new=AsyncMock(return_value=voices)):
        await cog.tts_voices.callback(cog, ctx, locale='sr')
    call = ctx.send.return_value.edit.call_args
    embed = call.kwargs.get('embed') or call.args[0]
    assert 'Nicholas' in embed.description
    assert 'Aria' not in embed.description


async def test_tts_voices_no_match(mock_bot, ctx):
    cog = _cog(mock_bot)
    voices = [{'ShortName': 'en-US-AriaNeural', 'FriendlyName': 'Aria', 'Locale': 'en-US'}]
    with patch('cogs.tts.edge_tts.list_voices', new=AsyncMock(return_value=voices)):
        await cog.tts_voices.callback(cog, ctx, locale='zz')
    call = ctx.send.return_value.edit.call_args
    embed = call.kwargs.get('embed') or call.args[0]
    assert '❌' in embed.title


# ---------------------------------------------------------------------------
# !tts rate
# ---------------------------------------------------------------------------

async def test_tts_rate_invalid(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.tts_rate.callback(cog, ctx, rate='fast')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_tts_rate_valid(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.tts.set_tts_rate') as mock_set:
        await cog.tts_rate.callback(cog, ctx, rate='+15%')
    mock_set.assert_called_once_with(ctx.guild.id, '+15%')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


async def test_tts_rate_negative(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.tts.set_tts_rate') as mock_set:
        await cog.tts_rate.callback(cog, ctx, rate='-20%')
    mock_set.assert_called_once_with(ctx.guild.id, '-20%')


# ---------------------------------------------------------------------------
# !tts stop
# ---------------------------------------------------------------------------

async def test_tts_stop(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.tts.VoiceStreamer') as MockStreamer:
        mock_streamer = AsyncMock()
        MockStreamer.return_value = mock_streamer
        await cog.tts_stop.callback(cog, ctx)
    mock_streamer.skip.assert_awaited_once()
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


# ---------------------------------------------------------------------------
# !tts show
# ---------------------------------------------------------------------------

async def test_tts_show(mock_bot, ctx):
    cog = _cog(mock_bot)
    with patch('cogs.tts.get_tts_voice', return_value='en-US-AriaNeural'):
        with patch('cogs.tts.get_tts_rate', return_value='+0%'):
            await cog.tts_show.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'AriaNeural' in embed.description
    assert '+0%' in embed.description
