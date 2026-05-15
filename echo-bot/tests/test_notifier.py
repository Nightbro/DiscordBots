from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from utils.notifier import Notifier


def _ctx(guild_id: int = 123456789) -> MagicMock:
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = guild_id
    ctx.guild.me = MagicMock(spec=discord.Member)
    ctx.message = MagicMock()
    ctx.message.add_reaction = AsyncMock()
    ctx.message.remove_reaction = AsyncMock()
    ctx.send = AsyncMock()
    return ctx


def _bot(guild_id: int = 123456789) -> MagicMock:
    bot = MagicMock()
    state = MagicMock()
    state.voice_client = None
    bot.get_guild_state = MagicMock(return_value=state)
    return bot


def _notifier(guild_id: int = 123456789) -> Notifier:
    return Notifier(_bot(guild_id), guild_id)


# ---------------------------------------------------------------------------
# Write mode (default: notify_write=True, notify_say=False)
# ---------------------------------------------------------------------------

async def test_success_sends_embed_write_mode():
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_write', return_value=True):
        with patch('utils.notifier.get_notify_say', return_value=False):
            await n.success(ctx, 'Done')
    ctx.send.assert_awaited_once()
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


async def test_error_sends_embed_write_mode():
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_write', return_value=True):
        with patch('utils.notifier.get_notify_say', return_value=False):
            await n.error(ctx, 'Oops', 'details here')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title
    assert 'details here' in embed.description


async def test_info_sends_embed_write_mode():
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_write', return_value=True):
        with patch('utils.notifier.get_notify_say', return_value=False):
            await n.info(ctx, 'Heads up')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'ℹ️' in embed.title


async def test_success_edits_loading_message():
    ctx = _ctx()
    loading = AsyncMock()
    n = _notifier()
    with patch('utils.notifier.get_notify_write', return_value=True):
        with patch('utils.notifier.get_notify_say', return_value=False):
            await n.success(ctx, 'Done', loading=loading)
    loading.edit.assert_awaited_once()
    ctx.send.assert_not_awaited()


# ---------------------------------------------------------------------------
# React mode (notify_write=False)
# ---------------------------------------------------------------------------

async def test_success_reacts_when_write_off():
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_write', return_value=False):
        with patch('utils.notifier.get_notify_say', return_value=False):
            await n.success(ctx, 'Done')
    ctx.send.assert_not_awaited()
    ctx.message.add_reaction.assert_awaited_once_with('✅')


async def test_error_reacts_when_write_off():
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_write', return_value=False):
        with patch('utils.notifier.get_notify_say', return_value=False):
            await n.error(ctx, 'Oops')
    ctx.message.add_reaction.assert_awaited_once_with('❌')


async def test_info_reacts_when_write_off():
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_write', return_value=False):
        with patch('utils.notifier.get_notify_say', return_value=False):
            await n.info(ctx, 'Note')
    ctx.message.add_reaction.assert_awaited_once_with('❓')


async def test_react_removes_loading_reaction():
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_write', return_value=False):
        with patch('utils.notifier.get_notify_say', return_value=False):
            await n.success(ctx, 'Done')
    ctx.message.remove_reaction.assert_awaited_once_with('⏳', ctx.guild.me)


# ---------------------------------------------------------------------------
# loading()
# ---------------------------------------------------------------------------

async def test_loading_sends_message_in_write_mode():
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_write', return_value=True):
        result = await n.loading(ctx, 'Please wait…')
    ctx.send.assert_awaited_once()
    assert result is not None


async def test_loading_reacts_and_returns_none_in_react_mode():
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_write', return_value=False):
        result = await n.loading(ctx, 'Please wait…')
    ctx.send.assert_not_awaited()
    ctx.message.add_reaction.assert_awaited_once_with('⏳')
    assert result is None


# ---------------------------------------------------------------------------
# say mode (notify_say=True)
# ---------------------------------------------------------------------------

async def test_say_speaks_when_in_voice():
    ctx = _ctx()
    bot = _bot()
    state = bot.get_guild_state.return_value
    vc = MagicMock()
    vc.is_connected.return_value = True
    state.voice_client = vc

    n = Notifier(bot, 123456789)
    with patch('utils.notifier.get_notify_write', return_value=True):
        with patch('utils.notifier.get_notify_say', return_value=True):
            with patch('utils.notifier.get_tts_voice', return_value='en-US-AriaNeural'):
                with patch('utils.notifier.get_tts_rate', return_value='+0%'):
                    with patch('utils.notifier.VoiceStreamer') as MockStreamer:
                        mock_streamer = AsyncMock()
                        MockStreamer.return_value = mock_streamer
                        with patch('utils.notifier.edge_tts') as mock_edge:
                            comm = AsyncMock()
                            mock_edge.Communicate.return_value = comm
                            await n.success(ctx, 'Track skipped')
    mock_streamer.interrupt.assert_awaited_once()


async def test_say_skipped_when_not_in_voice():
    ctx = _ctx()
    bot = _bot()
    # voice_client is None — bot not in voice
    bot.get_guild_state.return_value.voice_client = None

    n = Notifier(bot, 123456789)
    with patch('utils.notifier.get_notify_write', return_value=True):
        with patch('utils.notifier.get_notify_say', return_value=True):
            with patch('utils.notifier.VoiceStreamer') as MockStreamer:
                mock_streamer = AsyncMock()
                MockStreamer.return_value = mock_streamer
                await n.success(ctx, 'Track skipped')
    mock_streamer.interrupt.assert_not_awaited()


# ---------------------------------------------------------------------------
# track_card() — song details notifications (bypass notify_write / notify_say)
# ---------------------------------------------------------------------------

async def test_track_card_sends_embed_when_song_text_on():
    ctx = _ctx()
    n = _notifier()
    embed = MagicMock(spec=discord.Embed)
    with patch('utils.notifier.get_notify_song_text', return_value=True):
        with patch('utils.notifier.get_notify_song_voice', return_value=False):
            await n.track_card(ctx, embed, title='My Song')
    ctx.send.assert_awaited_once()


async def test_track_card_skips_embed_when_song_text_off():
    ctx = _ctx()
    n = _notifier()
    embed = MagicMock(spec=discord.Embed)
    with patch('utils.notifier.get_notify_song_text', return_value=False):
        with patch('utils.notifier.get_notify_song_voice', return_value=False):
            await n.track_card(ctx, embed, title='My Song')
    ctx.send.assert_not_awaited()


async def test_track_card_edits_loading_when_song_text_on():
    ctx = _ctx()
    n = _notifier()
    embed = MagicMock(spec=discord.Embed)
    loading = AsyncMock()
    with patch('utils.notifier.get_notify_song_text', return_value=True):
        with patch('utils.notifier.get_notify_song_voice', return_value=False):
            await n.track_card(ctx, embed, title='My Song', loading=loading)
    loading.edit.assert_awaited_once()
    ctx.send.assert_not_awaited()


async def test_track_card_deletes_loading_when_song_text_off():
    ctx = _ctx()
    n = _notifier()
    embed = MagicMock(spec=discord.Embed)
    loading = AsyncMock()
    with patch('utils.notifier.get_notify_song_text', return_value=False):
        with patch('utils.notifier.get_notify_song_voice', return_value=False):
            await n.track_card(ctx, embed, title='My Song', loading=loading)
    loading.delete.assert_awaited_once()
    ctx.send.assert_not_awaited()


async def test_track_card_speaks_when_song_voice_on():
    ctx = _ctx()
    bot = _bot()
    vc = MagicMock()
    vc.is_connected.return_value = True
    bot.get_guild_state.return_value.voice_client = vc
    n = Notifier(bot, 123456789)
    embed = MagicMock(spec=discord.Embed)
    with patch('utils.notifier.get_notify_song_text', return_value=False):
        with patch('utils.notifier.get_notify_song_voice', return_value=True):
            with patch('utils.notifier.get_tts_rate', return_value='+0%'):
                with patch('utils.notifier.VoiceStreamer') as MockStreamer:
                    mock_streamer = AsyncMock()
                    MockStreamer.return_value = mock_streamer
                    with patch('utils.notifier.edge_tts') as mock_edge:
                        mock_edge.Communicate.return_value = AsyncMock()
                        await n.track_card(ctx, embed, title='My Song')
    mock_streamer.interrupt.assert_awaited_once()


async def test_track_card_ignores_notify_write_when_song_text_on():
    """song_text=True sends the embed even when notify_write is False."""
    ctx = _ctx()
    n = _notifier()
    embed = MagicMock(spec=discord.Embed)
    with patch('utils.notifier.get_notify_song_text', return_value=True):
        with patch('utils.notifier.get_notify_song_voice', return_value=False):
            with patch('utils.notifier.get_notify_write', return_value=False):
                await n.track_card(ctx, embed, title='My Song')
    ctx.send.assert_awaited_once()


async def test_track_card_ignores_notify_say_when_song_voice_off():
    """song_voice=False suppresses TTS even when notify_say is True."""
    ctx = _ctx()
    bot = _bot()
    vc = MagicMock()
    vc.is_connected.return_value = True
    bot.get_guild_state.return_value.voice_client = vc
    n = Notifier(bot, 123456789)
    embed = MagicMock(spec=discord.Embed)
    with patch('utils.notifier.get_notify_song_text', return_value=True):
        with patch('utils.notifier.get_notify_song_voice', return_value=False):
            with patch('utils.notifier.get_notify_say', return_value=True):
                with patch('utils.notifier.VoiceStreamer') as MockStreamer:
                    mock_streamer = AsyncMock()
                    MockStreamer.return_value = mock_streamer
                    await n.track_card(ctx, embed, title='My Song')
    mock_streamer.interrupt.assert_not_awaited()


# ---------------------------------------------------------------------------
# say_loading() and say_response() — !say command notifications
# ---------------------------------------------------------------------------

async def test_say_loading_reacts_by_default():
    """Default notify_say_text=False → react with ⏳, return None."""
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_say_text', return_value=False):
        result = await n.say_loading(ctx, 'Synthesizing…')
    ctx.message.add_reaction.assert_awaited_once_with('⏳')
    ctx.send.assert_not_awaited()
    assert result is None


async def test_say_loading_sends_embed_when_text_on():
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_say_text', return_value=True):
        result = await n.say_loading(ctx, 'Synthesizing…')
    ctx.send.assert_awaited_once()
    assert result is not None


async def test_say_response_reacts_by_default():
    """Default notify_say_text=False → no embed, react with ✅."""
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_say_text', return_value=False):
        with patch('utils.notifier.get_notify_say_voice', return_value=False):
            await n.say_response(ctx, 'Speaking.')
    ctx.send.assert_not_awaited()
    ctx.message.add_reaction.assert_awaited_once_with('✅')


async def test_say_response_sends_embed_when_text_on():
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_say_text', return_value=True):
        with patch('utils.notifier.get_notify_say_voice', return_value=False):
            await n.say_response(ctx, 'Speaking.')
    ctx.send.assert_awaited_once()
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


async def test_say_response_edits_loading_when_text_on():
    ctx = _ctx()
    n = _notifier()
    loading = AsyncMock()
    with patch('utils.notifier.get_notify_say_text', return_value=True):
        with patch('utils.notifier.get_notify_say_voice', return_value=False):
            await n.say_response(ctx, 'Speaking.', loading=loading)
    loading.edit.assert_awaited_once()
    ctx.send.assert_not_awaited()


async def test_say_response_deletes_loading_when_text_off():
    ctx = _ctx()
    n = _notifier()
    loading = AsyncMock()
    with patch('utils.notifier.get_notify_say_text', return_value=False):
        with patch('utils.notifier.get_notify_say_voice', return_value=False):
            await n.say_response(ctx, 'Speaking.', loading=loading)
    loading.delete.assert_awaited_once()
    ctx.send.assert_not_awaited()


async def test_say_response_speaks_when_voice_on():
    ctx = _ctx()
    bot = _bot()
    vc = MagicMock()
    vc.is_connected.return_value = True
    bot.get_guild_state.return_value.voice_client = vc
    n = Notifier(bot, 123456789)
    with patch('utils.notifier.get_notify_say_text', return_value=False):
        with patch('utils.notifier.get_notify_say_voice', return_value=True):
            with patch('utils.notifier.get_tts_rate', return_value='+0%'):
                with patch('utils.notifier.VoiceStreamer') as MockStreamer:
                    mock_streamer = AsyncMock()
                    MockStreamer.return_value = mock_streamer
                    with patch('utils.notifier.edge_tts') as mock_edge:
                        mock_edge.Communicate.return_value = AsyncMock()
                        await n.say_response(ctx, 'Speaking.')
    mock_streamer.interrupt.assert_awaited_once()


async def test_say_response_ignores_notify_write_when_text_off():
    """notify_say_text=False suppresses embed even when notify_write is True."""
    ctx = _ctx()
    n = _notifier()
    with patch('utils.notifier.get_notify_say_text', return_value=False):
        with patch('utils.notifier.get_notify_say_voice', return_value=False):
            with patch('utils.notifier.get_notify_write', return_value=True):
                await n.say_response(ctx, 'Speaking.')
    ctx.send.assert_not_awaited()
    ctx.message.add_reaction.assert_awaited_once_with('✅')
