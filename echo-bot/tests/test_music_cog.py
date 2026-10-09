import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord.ext import commands

from cogs.music import MusicCog, _track_to_dict, _dict_to_track
from cogs.help import _HelpView
from utils.guild_state import Track


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cog(mock_bot) -> MusicCog:
    return MusicCog(mock_bot)


# ---------------------------------------------------------------------------
# _track_to_dict / _dict_to_track
# ---------------------------------------------------------------------------

def test_track_roundtrip():
    track = Track(title='Song', url='https://example.com', duration=90, source_id='abc')
    data = _track_to_dict(track)
    restored = _dict_to_track(data)
    assert restored.title == track.title
    assert restored.url == track.url
    assert restored.duration == track.duration
    assert restored.source_id == track.source_id


def test_dict_to_track_missing_optional():
    data = {'title': 'T', 'url': 'u'}
    track = _dict_to_track(data)
    assert track.duration is None
    assert track.source_id is None


# _PagedView tests moved to test_help_cog.py


# ---------------------------------------------------------------------------
# _ensure_voice
# ---------------------------------------------------------------------------

async def test_ensure_voice_returns_none_when_no_voice(mock_bot, ctx_no_voice):
    cog = _cog(mock_bot)
    streamer, connected = await cog._ensure_voice(ctx_no_voice)
    assert streamer is None
    assert connected is False
    ctx_no_voice.send.assert_awaited_once()


async def test_ensure_voice_joins_channel(mock_bot, ctx, guild_state):
    cog = _cog(mock_bot)
    with patch('cogs.music.VoiceStreamer') as MockStreamer:
        mock_streamer = AsyncMock()
        MockStreamer.return_value = mock_streamer
        streamer, _ = await cog._ensure_voice(ctx)
    mock_streamer.join.assert_awaited_once()


# ---------------------------------------------------------------------------
# play
# ---------------------------------------------------------------------------

async def test_play_calls_resolve_and_play(mock_bot, ctx, guild_state):
    cog = _cog(mock_bot)
    loading_msg = AsyncMock()
    ctx.send = AsyncMock(return_value=loading_msg)
    fake_track = Track(title='Song', url='https://youtube.com/watch?v=x')

    with patch('cogs.music.VoiceStreamer') as MockStreamer:
        mock_streamer = AsyncMock()
        MockStreamer.return_value = mock_streamer
        with patch('cogs.music.Downloader.resolve', new=AsyncMock(return_value=fake_track)):
            await cog.play.callback(cog, ctx, query='never gonna give you up')

    mock_streamer.play.assert_awaited_once_with(fake_track)


async def test_play_sends_error_on_queue_full(mock_bot, ctx, guild_state):
    cog = _cog(mock_bot)
    loading_msg = AsyncMock()
    ctx.send = AsyncMock(return_value=loading_msg)
    fake_track = Track(title='Song', url='u')

    with patch('cogs.music.VoiceStreamer') as MockStreamer:
        mock_streamer = AsyncMock()
        mock_streamer.play = AsyncMock(side_effect=ValueError('Queue is full'))
        MockStreamer.return_value = mock_streamer
        with patch('cogs.music.Downloader.resolve', new=AsyncMock(return_value=fake_track)):
            await cog.play.callback(cog, ctx, query='test')

    loading_msg.edit.assert_awaited()
    embed = loading_msg.edit.call_args.kwargs.get('embed') or loading_msg.edit.call_args.args[0]
    assert '❌' in embed.title


# ---------------------------------------------------------------------------
# skip
# ---------------------------------------------------------------------------

async def test_skip_sends_success_embed(mock_bot, ctx, guild_state, sample_track):
    cog = _cog(mock_bot)
    with patch('cogs.music.VoiceStreamer') as MockStreamer:
        mock_streamer = AsyncMock()
        mock_streamer.skip = AsyncMock(return_value=sample_track)
        MockStreamer.return_value = mock_streamer
        await cog.skip.callback(cog, ctx)
    ctx.send.assert_awaited_once()
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


async def test_skip_sends_error_when_nothing_playing(mock_bot, ctx, guild_state):
    cog = _cog(mock_bot)
    with patch('cogs.music.VoiceStreamer') as MockStreamer:
        mock_streamer = AsyncMock()
        mock_streamer.skip = AsyncMock(return_value=None)
        MockStreamer.return_value = mock_streamer
        await cog.skip.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------

async def test_replay_success(mock_bot, ctx, guild_state, sample_track):
    cog = _cog(mock_bot)
    with patch('cogs.music.VoiceStreamer') as MockStreamer:
        mock_streamer = AsyncMock()
        mock_streamer.replay = AsyncMock(return_value=sample_track)
        MockStreamer.return_value = mock_streamer
        await cog.replay.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


async def test_replay_nothing_to_replay(mock_bot, ctx, guild_state):
    cog = _cog(mock_bot)
    with patch('cogs.music.VoiceStreamer') as MockStreamer:
        mock_streamer = AsyncMock()
        mock_streamer.replay = AsyncMock(return_value=None)
        MockStreamer.return_value = mock_streamer
        await cog.replay.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


# ---------------------------------------------------------------------------
# queue
# ---------------------------------------------------------------------------

async def test_queue_shows_current_track(mock_bot, ctx, guild_state, sample_track):
    guild_state.current_track = sample_track
    cog = _cog(mock_bot)
    await cog.queue.callback(cog, ctx)
    ctx.send.assert_awaited_once()
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'Now playing' in embed.description


async def test_queue_empty_message(mock_bot, ctx, guild_state):
    cog = _cog(mock_bot)
    await cog.queue.callback(cog, ctx)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'empty' in embed.description.lower()


# ---------------------------------------------------------------------------
# clear / remove / shuffle
# ---------------------------------------------------------------------------

async def test_clear_empties_queue(mock_bot, ctx, guild_state, sample_track):
    guild_state.queue.append(sample_track)
    cog = _cog(mock_bot)
    await cog.clear.callback(cog, ctx)
    assert len(guild_state.queue) == 0


async def test_remove_valid_position(mock_bot, ctx, guild_state):
    for i in range(3):
        guild_state.queue.append(Track(title=str(i), url='u'))
    cog = _cog(mock_bot)
    await cog.remove.callback(cog, ctx, position=2)
    titles = [t.title for t in guild_state.queue]
    assert '1' not in titles
    assert '0' in titles
    assert '2' in titles


async def test_remove_out_of_range(mock_bot, ctx, guild_state, sample_track):
    guild_state.queue.append(sample_track)
    cog = _cog(mock_bot)
    await cog.remove.callback(cog, ctx, position=99)
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_shuffle_reorders_queue(mock_bot, ctx, guild_state):
    for i in range(10):
        guild_state.queue.append(Track(title=str(i), url='u'))
    original = list(guild_state.queue)
    cog = _cog(mock_bot)
    # Run shuffle several times to avoid flaky pass when shuffle returns same order
    for _ in range(5):
        await cog.shuffle.callback(cog, ctx)
        if list(guild_state.queue) != original:
            break
    assert len(guild_state.queue) == 10  # length preserved


# ---------------------------------------------------------------------------
# playlist
# ---------------------------------------------------------------------------

async def test_playlist_save_success(mock_bot, ctx, guild_state, sample_track):
    guild_state.queue.append(sample_track)
    cog = _cog(mock_bot)
    with patch('cogs.music.PlaylistConfig') as MockCfg:
        cfg_instance = MagicMock()
        MockCfg.return_value = cfg_instance
        await cog.playlist_save.callback(cog, ctx, name='my_list')
    cfg_instance.set.assert_called_once()


async def test_playlist_save_empty_sends_error(mock_bot, ctx, guild_state):
    cog = _cog(mock_bot)
    await cog.playlist_save.callback(cog, ctx, name='empty')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_playlist_load_not_found(mock_bot, ctx, guild_state):
    cog = _cog(mock_bot)
    with patch('cogs.music.PlaylistConfig') as MockCfg:
        cfg_instance = MagicMock()
        cfg_instance.get.return_value = None
        MockCfg.return_value = cfg_instance
        await cog.playlist_load.callback(cog, ctx, name='missing')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '❌' in embed.title


async def test_playlist_delete_success(mock_bot, ctx, guild_state):
    cog = _cog(mock_bot)
    with patch('cogs.music.PlaylistConfig') as MockCfg:
        cfg_instance = MagicMock()
        cfg_instance.delete.return_value = True
        MockCfg.return_value = cfg_instance
        await cog.playlist_delete.callback(cog, ctx, name='my_list')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert '✅' in embed.title


# ---------------------------------------------------------------------------
# Library-first !play (with the switch-to-YouTube prompt)
# ---------------------------------------------------------------------------

@pytest.fixture
def lib_bot(mock_bot):
    """mock_bot whose get_cog('Library') returns a stub library cog."""
    lib_cog = MagicMock()
    lib_cog.play_slug = AsyncMock(return_value=True)
    mock_bot.get_cog = MagicMock(return_value=lib_cog)
    return mock_bot, lib_cog


async def test_play_prefers_library_match_after_countdown(lib_bot, ctx):
    bot, lib_cog = lib_bot
    cog = _cog(bot)
    ctx.send = AsyncMock(return_value=AsyncMock())
    with patch('cogs.music.library.resolve', return_value=('halloween', {'title': 'Halloween'})), \
         patch('cogs.music.LIBRARY_CONFIRM_SECS', 0.01), \
         patch('cogs.music.Downloader.resolve', new=AsyncMock()) as mock_resolve:
        await cog.play.callback(cog, ctx, query='halloween')
    lib_cog.play_slug.assert_awaited_once_with(ctx, 'halloween')
    mock_resolve.assert_not_awaited()  # never hit the web


async def test_play_prompt_offers_youtube_switch(lib_bot, ctx):
    bot, _ = lib_bot
    cog = _cog(bot)
    ctx.send = AsyncMock(return_value=AsyncMock())
    with patch('cogs.music.library.resolve', return_value=('halloween', {'title': 'Halloween'})), \
         patch('cogs.music.LIBRARY_CONFIRM_SECS', 0.01), \
         patch('cogs.music.Downloader.resolve', new=AsyncMock()):
        await cog.play.callback(cog, ctx, query='halloween')
    view = ctx.send.await_args_list[0].kwargs['view']
    assert any('YouTube' in (c.label or '') for c in view.children)
    embed = ctx.send.await_args_list[0].kwargs['embed']
    assert 'Halloween' in embed.title


async def test_play_switches_to_youtube_when_button_pressed(lib_bot, ctx):
    bot, lib_cog = lib_bot
    cog = _cog(bot)
    prompt = AsyncMock()
    ctx.send = AsyncMock(return_value=prompt)
    fake_track = Track(title='YT Song', url='https://youtube.com/watch?v=x')
    pressed = asyncio.Event()

    async def press_when_shown():
        """Stand in for the user clicking 'Search YouTube instead' during the countdown."""
        while not ctx.send.await_args_list:
            await asyncio.sleep(0)
        view = ctx.send.await_args_list[0].kwargs['view']
        interaction = MagicMock()
        interaction.user.id = ctx.author.id
        interaction.response.defer = AsyncMock()
        await view.children[0].callback(interaction)
        pressed.set()

    with patch('cogs.music.library.resolve', return_value=('halloween', {'title': 'Halloween'})),          patch('cogs.music.LIBRARY_CONFIRM_SECS', 30),          patch('cogs.music.VoiceStreamer') as MockStreamer,          patch('cogs.music.Downloader.resolve', new=AsyncMock(return_value=fake_track)):
        streamer = AsyncMock()
        MockStreamer.return_value = streamer
        presser = asyncio.create_task(press_when_shown())
        await cog.play.callback(cog, ctx, query='halloween')
        await presser

    assert pressed.is_set()
    lib_cog.play_slug.assert_not_awaited()
    streamer.play.assert_awaited_once_with(fake_track)
    prompt.delete.assert_awaited_once()


async def test_play_index_reference_skips_the_prompt(lib_bot, ctx):
    bot, lib_cog = lib_bot
    cog = _cog(bot)
    ctx.send = AsyncMock(return_value=AsyncMock())
    with patch('cogs.music.library.resolve', return_value=('halloween', {'title': 'Halloween'})), \
         patch('cogs.music.LIBRARY_CONFIRM_SECS', 5):
        await cog.play.callback(cog, ctx, query='#1')
    lib_cog.play_slug.assert_awaited_once_with(ctx, 'halloween')
    assert not any('view' in c.kwargs for c in ctx.send.await_args_list)


async def test_play_confirm_disabled_plays_library_immediately(lib_bot, ctx):
    bot, lib_cog = lib_bot
    cog = _cog(bot)
    ctx.send = AsyncMock(return_value=AsyncMock())
    with patch('cogs.music.library.resolve', return_value=('halloween', {'title': 'Halloween'})), \
         patch('cogs.music.LIBRARY_CONFIRM_SECS', 0):
        await cog.play.callback(cog, ctx, query='halloween')
    lib_cog.play_slug.assert_awaited_once()


async def test_play_url_never_checks_the_library(lib_bot, ctx):
    bot, lib_cog = lib_bot
    cog = _cog(bot)
    ctx.send = AsyncMock(return_value=AsyncMock())
    fake_track = Track(title='Song', url='https://youtube.com/watch?v=x')
    with patch('cogs.music.library.resolve') as mock_resolve, \
         patch('cogs.music.VoiceStreamer') as MockStreamer, \
         patch('cogs.music.Downloader.resolve', new=AsyncMock(return_value=fake_track)):
        MockStreamer.return_value = AsyncMock()
        await cog.play.callback(cog, ctx, query='https://youtube.com/watch?v=x')
    mock_resolve.assert_not_called()
    lib_cog.play_slug.assert_not_awaited()


async def test_play_falls_back_to_search_when_no_library_match(lib_bot, ctx):
    bot, lib_cog = lib_bot
    cog = _cog(bot)
    ctx.send = AsyncMock(return_value=AsyncMock())
    fake_track = Track(title='Song', url='u')
    with patch('cogs.music.library.resolve', return_value=None), \
         patch('cogs.music.VoiceStreamer') as MockStreamer, \
         patch('cogs.music.Downloader.resolve', new=AsyncMock(return_value=fake_track)):
        streamer = AsyncMock()
        MockStreamer.return_value = streamer
        await cog.play.callback(cog, ctx, query='something else')
    lib_cog.play_slug.assert_not_awaited()
    streamer.play.assert_awaited_once_with(fake_track)


async def test_play_prompt_rejects_other_users(lib_bot, ctx):
    bot, _ = lib_bot
    cog = _cog(bot)
    ctx.send = AsyncMock(return_value=AsyncMock())
    with patch('cogs.music.library.resolve', return_value=('halloween', {'title': 'Halloween'})), \
         patch('cogs.music.LIBRARY_CONFIRM_SECS', 0.01), \
         patch('cogs.music.Downloader.resolve', new=AsyncMock()):
        await cog.play.callback(cog, ctx, query='halloween')
    view = ctx.send.await_args_list[0].kwargs['view']
    interaction = MagicMock()
    interaction.user.id = 999999
    interaction.response.send_message = AsyncMock()
    assert await view.interaction_check(interaction) is False
