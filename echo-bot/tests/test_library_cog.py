import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.library import LibraryCog, _DownloadConfirmView, _LibraryView, _list_embed
from utils.guild_state import Track
from utils import library


@pytest.fixture(autouse=True)
def library_paths(tmp_path):
    with patch('utils.library.LIBRARY_DIR', tmp_path / 'library'), \
         patch('utils.config.LIBRARY_CONFIG_FILE', tmp_path / 'library_config.json'):
        yield


@pytest.fixture
def cog(mock_bot):
    return LibraryCog(mock_bot)


@pytest.fixture
def lctx(ctx):
    ctx.message = MagicMock()
    ctx.message.attachments = []
    ctx.message.reference = None
    ctx.author.display_name = 'Tester'
    return ctx


def _attachment(filename='song.mp3', size=1024):
    att = MagicMock(spec=discord.Attachment)
    att.filename = filename
    att.size = size

    async def save(dest):
        dest.write_bytes(b'x' * size)
    att.save = AsyncMock(side_effect=save)
    return att


def _add(guild_id, title, **kw):
    slug = library.slugify(title)
    path = library.guild_dir(guild_id) / f'{slug}.mp3'
    path.write_bytes(b'x' * kw.pop('size', 1024))
    return library.add_track(
        guild_id, title, path, duration=kw.pop('duration', 180),
        added_by=1, added_by_name='Tester',
    )


async def _save(cog, ctx, name='', attachment=None, duration=180):
    ctx.message.attachments = [attachment or _attachment()]
    with patch('utils.library.probe_duration', new=AsyncMock(return_value=duration)):
        await cog.save.callback(cog, ctx, name=name)


def _last_embed(ctx):
    return ctx.send.await_args.kwargs['embed']


# ---------------------------------------------------------------------------
# !save
# ---------------------------------------------------------------------------

async def test_save_stores_track_and_confirms(cog, lctx):
    await _save(cog, lctx, 'Halloween', duration=192)
    meta = library.get_track(123456789, 'halloween')
    assert meta['title'] == 'Halloween'
    assert meta['duration'] == 192
    assert library.track_path(123456789, 'halloween').exists()
    assert 'Halloween' in _last_embed(lctx).title


async def test_save_without_name_uses_filename(cog, lctx):
    await _save(cog, lctx, attachment=_attachment('My Song.mp3'))
    assert library.get_track(123456789, 'my-song')['title'] == 'My Song'


async def test_save_rejects_missing_attachment(cog, lctx):
    await cog.save.callback(cog, lctx, name='X')
    assert '❌' in _last_embed(lctx).title
    assert library.track_list(123456789) == []


async def test_save_rejects_bad_format(cog, lctx):
    lctx.message.attachments = [_attachment('virus.exe')]
    await cog.save.callback(cog, lctx, name='X')
    assert '❌' in _last_embed(lctx).title
    assert library.track_list(123456789) == []


async def test_save_rejects_duplicate_name(cog, lctx):
    await _save(cog, lctx, 'Halloween')
    await _save(cog, lctx, 'halloween')
    assert '❌' in _last_embed(lctx).title
    assert len(library.track_list(123456789)) == 1


async def test_save_rejects_when_track_limit_reached(cog, lctx):
    with patch('utils.library.LIBRARY_MAX_TRACKS', 1):
        await _save(cog, lctx, 'One')
        await _save(cog, lctx, 'Two')
    assert '❌' in _last_embed(lctx).title
    assert len(library.track_list(123456789)) == 1


async def test_save_cleans_up_file_when_registration_fails(cog, lctx):
    lctx.message.attachments = [_attachment()]
    with patch('utils.library.probe_duration', new=AsyncMock(return_value=1)), \
         patch('utils.library.add_track', side_effect=RuntimeError('disk full')):
        await cog.save.callback(cog, lctx, name='Boom')
    assert not (library.guild_dir(123456789) / 'boom.mp3').exists()
    assert '❌' in _last_embed(lctx).title


async def test_save_takes_attachment_from_replied_message(cog, lctx):
    replied = MagicMock(spec=discord.Message)
    replied.attachments = [_attachment('Replied.mp3')]
    lctx.message.reference = MagicMock(resolved=replied, message_id=99)
    with patch('utils.library.probe_duration', new=AsyncMock(return_value=10)):
        await cog.save.callback(cog, lctx, name='From Reply')
    assert library.get_track(123456789, 'from-reply') is not None


async def test_save_is_per_guild(cog, lctx):
    await _save(cog, lctx, 'Mine')
    lctx.guild.id = 999
    await _save(cog, lctx, 'Theirs')
    assert [m['title'] for _, m in library.track_list(123456789)] == ['Mine']
    assert [m['title'] for _, m in library.track_list(999)] == ['Theirs']


# ---------------------------------------------------------------------------
# !library listing
# ---------------------------------------------------------------------------

def test_list_embed_empty():
    embed, shown = _list_embed(1, 0)
    assert shown == []
    assert 'No tracks' in embed.description


def test_list_embed_numbers_and_pages():
    for i in range(12):
        _add(1, f'Track {i:02d}')
    embed, shown = _list_embed(1, 0)
    assert len(shown) == 10
    assert '` 1.`' in embed.description
    assert 'Page 1/2' in embed.description
    embed2, shown2 = _list_embed(1, 1)
    assert len(shown2) == 2
    assert '`11.`' in embed2.description


def test_list_embed_clamps_out_of_range_page():
    _add(1, 'Only')
    embed, shown = _list_embed(1, 5)
    assert len(shown) == 1


async def test_library_command_sends_view(cog, lctx):
    _add(123456789, 'Halloween')
    await cog.library_cmd.callback(cog, lctx, query='')
    view = lctx.send.await_args.kwargs['view']
    assert isinstance(view, _LibraryView)
    assert any(isinstance(c, discord.ui.Select) for c in view.children)


async def test_library_command_has_no_view_when_empty(cog, lctx):
    await cog.library_cmd.callback(cog, lctx, query='')
    assert lctx.send.await_args.kwargs['view'] is None


# ---------------------------------------------------------------------------
# Playing
# ---------------------------------------------------------------------------

async def test_play_slug_queues_track(cog, lctx):
    slug = _add(123456789, 'Halloween')
    with patch('cogs.library.VoiceStreamer') as MockStreamer:
        streamer = AsyncMock()
        MockStreamer.return_value = streamer
        assert await cog.play_slug(lctx, slug) is True
    track = streamer.play.await_args.args[0]
    assert track.title == 'Halloween'
    assert library.get_track(123456789, slug)['plays'] == 1


async def test_play_slug_requires_voice(cog, lctx):
    slug = _add(123456789, 'Halloween')
    lctx.author.voice = None
    with patch('cogs.library.VoiceStreamer') as MockStreamer:
        streamer = AsyncMock()
        MockStreamer.return_value = streamer
        assert await cog.play_slug(lctx, slug) is False
    streamer.play.assert_not_awaited()


async def test_play_slug_reports_missing_file(cog, lctx):
    slug = _add(123456789, 'Halloween')
    library.track_path(123456789, slug).unlink()
    assert await cog.play_slug(lctx, slug) is False
    assert '❌' in _last_embed(lctx).title


async def test_library_command_with_name_plays(cog, lctx):
    _add(123456789, 'Halloween')
    with patch.object(LibraryCog, 'play_slug', new=AsyncMock(return_value=True)) as mock_play:
        await cog.library_cmd.callback(cog, lctx, query='hallo')
    mock_play.assert_awaited_once()
    assert mock_play.await_args.args[1] == 'halloween'


async def test_library_play_by_index(cog, lctx):
    _add(123456789, 'apple')
    _add(123456789, 'banana')
    with patch.object(LibraryCog, 'play_slug', new=AsyncMock(return_value=True)) as mock_play:
        await cog.library_play.callback(cog, lctx, query='#2')
    assert mock_play.await_args.args[1] == 'banana'


async def test_library_play_unknown_name(cog, lctx):
    with patch.object(LibraryCog, 'play_slug', new=AsyncMock()) as mock_play:
        await cog.library_play.callback(cog, lctx, query='nope')
    mock_play.assert_not_awaited()
    assert '❌' in _last_embed(lctx).title


# ---------------------------------------------------------------------------
# remove / rename / info
# ---------------------------------------------------------------------------

async def test_remove_deletes_track(cog, lctx):
    slug = _add(123456789, 'Halloween')
    path = library.track_path(123456789, slug)
    await cog.library_remove.callback(cog, lctx, query='#1')
    assert library.get_track(123456789, slug) is None
    assert not path.exists()


async def test_remove_unknown_track(cog, lctx):
    await cog.library_remove.callback(cog, lctx, query='nope')
    assert '❌' in _last_embed(lctx).title


async def test_rename_track(cog, lctx):
    _add(123456789, 'Old')
    await cog.library_rename.callback(cog, lctx, '#1', new_title='Brand New')
    assert library.get_track(123456789, 'brand-new')['title'] == 'Brand New'


async def test_rename_rejects_taken_name(cog, lctx):
    _add(123456789, 'One')
    _add(123456789, 'Two')
    await cog.library_rename.callback(cog, lctx, 'One', new_title='Two')
    assert '❌' in _last_embed(lctx).title
    assert library.get_track(123456789, 'one') is not None


async def test_info_shows_details(cog, lctx):
    _add(123456789, 'Halloween', duration=192)
    await cog.library_info.callback(cog, lctx, query='halloween')
    embed = _last_embed(lctx)
    assert 'Halloween' in embed.title
    assert '3:12' in embed.description
    assert 'Tester' in embed.description


# ---------------------------------------------------------------------------
# Dropdown view
# ---------------------------------------------------------------------------

async def test_view_rejects_other_users(cog):
    _add(1, 'Halloween')
    view = _LibraryView(cog, 1, user_id=42)
    interaction = MagicMock()
    interaction.user.id = 7
    interaction.response.send_message = AsyncMock()
    assert await view.interaction_check(interaction) is False
    assert interaction.response.send_message.await_args.kwargs['ephemeral'] is True


async def test_view_allows_owner(cog):
    view = _LibraryView(cog, 1, user_id=42)
    interaction = MagicMock()
    interaction.user.id = 42
    assert await view.interaction_check(interaction) is True


async def test_view_pick_queues_track(cog):
    slug = _add(1, 'Halloween')
    view = _LibraryView(cog, 1, user_id=42)
    interaction = MagicMock()
    interaction.data = {'values': [slug]}
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.voice = MagicMock()
    with patch('cogs.library.VoiceStreamer') as MockStreamer:
        streamer = AsyncMock()
        MockStreamer.return_value = streamer
        await view._on_pick(interaction)
    assert streamer.play.await_args.args[0].title == 'Halloween'
    interaction.followup.send.assert_awaited_once()


async def test_view_pick_without_voice_warns(cog):
    slug = _add(1, 'Halloween')
    view = _LibraryView(cog, 1, user_id=42)
    interaction = MagicMock()
    interaction.data = {'values': [slug]}
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.voice = None
    with patch('cogs.library.VoiceStreamer') as MockStreamer:
        streamer = AsyncMock()
        MockStreamer.return_value = streamer
        await view._on_pick(interaction)
    streamer.play.assert_not_awaited()
    assert interaction.followup.send.await_args.kwargs['ephemeral'] is True


def test_view_has_page_buttons_only_when_needed(cog):
    _add(1, 'Only')
    assert not [c for c in _LibraryView(cog, 1, 42).children if isinstance(c, discord.ui.Button)]
    for i in range(12):
        _add(1, f'Track {i:02d}')
    buttons = [c for c in _LibraryView(cog, 1, 42).children if isinstance(c, discord.ui.Button)]
    assert len(buttons) == 2
    assert buttons[0].disabled is True   # first page: ◀ disabled
    assert buttons[1].disabled is False


# ---------------------------------------------------------------------------
# !download / !download play
# ---------------------------------------------------------------------------

@pytest.fixture
def write_off(monkeypatch):
    """Disable the write notifier so loading messages are not created.

    Without this, notifier.loading() calls ctx.send() and returns a MagicMock;
    the cog then awaits loading.edit(), which works at runtime (real discord.Message)
    but would need an AsyncMock in tests.  With write_off, loading() returns None,
    success/error fall back to reactions (try/except so they're silent), and
    any confirmation view is sent via ctx.send() where tests can inspect it.
    """
    monkeypatch.setattr('utils.notifier.get_notify_write', lambda gid: False)


def _dl_track(title: str = 'Test Song', duration: int = 180) -> Track:
    return Track(title=title, url='https://yt.be/x', duration=duration, source_id='abc123')


async def _run_download(cog, ctx, tmp_path, query='Test Song', play_after=False, duration=180):
    track = _dl_track(title=query, duration=duration)
    dl_file = tmp_path / 'abc123.mp3'
    dl_file.write_bytes(b'x' * 1024)
    with patch('cogs.library.Downloader.resolve', new=AsyncMock(return_value=track)), \
         patch('cogs.library.Downloader.download', new=AsyncMock(return_value=dl_file)), \
         patch('utils.library.probe_duration', new=AsyncMock(return_value=duration)):
        if play_after:
            await cog.download_play.callback(cog, ctx, query=query)
        else:
            await cog.download_cmd.callback(cog, ctx, query=query)


async def test_download_saves_track_to_library(cog, lctx, tmp_path, write_off):
    await _run_download(cog, lctx, tmp_path)
    meta = library.get_track(123456789, 'test-song')
    assert meta is not None
    assert meta['title'] == 'Test Song'
    assert library.track_path(123456789, 'test-song').exists()


async def test_download_no_query_shows_error(cog, lctx, write_off):
    await cog.download_cmd.callback(cog, lctx, query='')
    assert library.track_list(123456789) == []


async def test_download_resolve_failure_reports_error(cog, lctx, write_off):
    with patch('cogs.library.Downloader.resolve', new=AsyncMock(side_effect=ValueError('no results'))):
        await cog.download_cmd.callback(cog, lctx, query='impossible query')
    assert library.track_list(123456789) == []


async def test_download_similar_match_shows_confirmation_view(cog, lctx, tmp_path, write_off):
    _add(123456789, 'Test Song')
    track = _dl_track('Test Song')
    with patch('cogs.library.Downloader.resolve', new=AsyncMock(return_value=track)):
        await cog.download_cmd.callback(cog, lctx, query='Test Song')
    # With write_off, loading=None → confirmation sent via ctx.send(view=...)
    view = lctx.send.await_args.kwargs.get('view')
    assert isinstance(view, _DownloadConfirmView)
    assert len(library.track_list(123456789)) == 1


async def test_download_respects_track_count_limit(cog, lctx, tmp_path, write_off):
    with patch('utils.library.LIBRARY_MAX_TRACKS', 1):
        _add(123456789, 'Existing')
        await _run_download(cog, lctx, tmp_path)
    assert len(library.track_list(123456789)) == 1


async def test_download_respects_storage_limit(cog, lctx, tmp_path, write_off):
    with patch('utils.library.LIBRARY_MAX_TOTAL_MB', 0):
        await _run_download(cog, lctx, tmp_path)
    assert library.track_list(123456789) == []


async def test_download_adds_suffix_on_slug_collision(cog, lctx, tmp_path, write_off):
    _add(123456789, 'Test Song')
    track = _dl_track('Test Song')
    dl_file = tmp_path / 'abc123.mp3'
    dl_file.write_bytes(b'x' * 1024)
    with patch('cogs.library.Downloader.resolve', new=AsyncMock(return_value=track)), \
         patch('cogs.library.Downloader.download', new=AsyncMock(return_value=dl_file)), \
         patch('utils.library.probe_duration', new=AsyncMock(return_value=60)), \
         patch('utils.library.find_all', return_value=[]):
        await cog.download_cmd.callback(cog, lctx, query='Test Song')
    # Original slug taken → suffix appended
    assert library.get_track(123456789, 'test-song-2') is not None


async def test_download_play_saves_and_queues_track(cog, lctx, tmp_path, write_off):
    with patch.object(LibraryCog, 'play_slug', new=AsyncMock(return_value=True)) as mock_play:
        await _run_download(cog, lctx, tmp_path, play_after=True)
    meta = library.get_track(123456789, 'test-song')
    assert meta is not None
    mock_play.assert_awaited_once()


async def test_download_confirm_view_on_download_saves_track(cog, lctx, tmp_path, write_off):
    _add(123456789, 'Test Song')
    track = _dl_track('Test Song')
    matches = library.find_all(123456789, 'Test Song')
    view = _DownloadConfirmView(cog, lctx, track, False, matches)
    dl_file = tmp_path / 'abc123.mp3'
    dl_file.write_bytes(b'x' * 1024)
    interaction = MagicMock()
    interaction.response.edit_message = AsyncMock()
    with patch('cogs.library.Downloader.download', new=AsyncMock(return_value=dl_file)), \
         patch('utils.library.probe_duration', new=AsyncMock(return_value=60)):
        await view._on_download(interaction)
    # A second track (suffix) or new entry should be in the library
    assert len(library.track_list(123456789)) == 2


async def test_download_confirm_view_on_use_library_plays(cog, lctx, tmp_path, write_off):
    _add(123456789, 'Test Song')
    track = _dl_track('Test Song')
    matches = library.find_all(123456789, 'Test Song')
    view = _DownloadConfirmView(cog, lctx, track, False, matches)
    interaction = MagicMock()
    interaction.response.edit_message = AsyncMock()
    with patch.object(LibraryCog, 'play_slug', new=AsyncMock(return_value=True)) as mock_play:
        await view._on_use_library(interaction)
    mock_play.assert_awaited_once_with(lctx, 'test-song')
