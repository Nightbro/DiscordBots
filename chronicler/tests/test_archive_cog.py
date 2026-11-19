"""The archive cog: option parsing, permission gates, and a real export."""

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.archive import ArchiveCog, missing_permissions, parse_options
from utils import archive
from utils.archive import ArchiveError

WHEN = datetime(2026, 11, 19, 14, 30, tzinfo=timezone.utc)
START = 123456789012345678
END = 223456789012345678


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

def _attachment(filename='shot.png', payload=b'\x89PNG' + b'0' * 60):
    att = MagicMock(spec=discord.Attachment)
    att.filename = filename
    att.size = len(payload)
    att.content_type = 'image/png' if filename.endswith('.png') else 'application/octet-stream'

    async def save(dest, **_kwargs):
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return len(payload)

    att.save = AsyncMock(side_effect=save)
    return att


def _message(mid, content='hello', attachments=(), author='Ivan'):
    msg = MagicMock(spec=discord.Message)
    msg.id = mid
    msg.content = content
    msg.created_at = WHEN
    msg.edited_at = None
    msg.attachments = list(attachments)
    msg.author = MagicMock()
    msg.author.id = 42
    msg.author.display_name = author
    return msg


def _channel(messages=(), name='general', channel_id=777000111, **perms):
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.name = name
    channel.mention = f'#{name}'
    channel.send = AsyncMock()
    channel.delete_messages = AsyncMock()
    channel.get_partial_message = MagicMock(
        side_effect=lambda mid: MagicMock(id=mid, delete=AsyncMock())
    )

    granted = {
        'view_channel': True, 'read_message_history': True,
        'send_messages': True, 'attach_files': True,
        'manage_messages': True,
    }
    granted.update(perms)
    resolved = MagicMock(**granted)
    channel.permissions_for = MagicMock(return_value=resolved)

    ordered = list(messages)

    def history(**kwargs):
        seq = list(ordered)
        if kwargs.get('oldest_first') is False:
            seq.reverse()
        limit = kwargs.get('limit')
        if limit:
            seq = seq[:limit]

        async def gen():
            for item in seq:
                yield item

        return gen()

    channel.history = MagicMock(side_effect=history)
    return channel


def _ctx(channel, guild_id=123456789, filesize_limit=8 * 1024 * 1024, can_purge=True):
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = guild_id
    ctx.guild.name = 'The Table'
    ctx.guild.me = MagicMock()
    ctx.guild.filesize_limit = filesize_limit
    ctx.channel = channel
    # spec=Member so the cog's isinstance check sees a real member and reads
    # the permission rather than falling through to the owner check.
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 42
    ctx.author.display_name = 'Ivan'
    ctx.author.guild_permissions = MagicMock(manage_messages=can_purge)
    progress = MagicMock()
    progress.edit = AsyncMock()
    progress.delete = AsyncMock()
    ctx.send = AsyncMock(return_value=progress)
    ctx.progress = progress
    return ctx


def _final_embed(ctx):
    """The embed the user is left looking at — usually the edited progress one."""
    if ctx.progress.edit.await_args is not None:
        return ctx.progress.edit.await_args.kwargs['embed']
    return ctx.send.await_args.kwargs['embed']


def _cog(mock_bot) -> ArchiveCog:
    return ArchiveCog(mock_bot)


# ---------------------------------------------------------------------------
# parse_options
# ---------------------------------------------------------------------------

def test_parse_last():
    spec, purge = parse_options('last 500')
    assert (spec.limit, spec.start_id, purge) == (500, None, False)


def test_parse_last_is_case_insensitive():
    assert parse_options('LAST 20')[0].limit == 20


def test_parse_from_only():
    spec, _ = parse_options(f'from {START}')
    assert (spec.start_id, spec.end_id) == (START, None)


def test_parse_from_to():
    spec, _ = parse_options(f'from {START} to {END}')
    assert (spec.start_id, spec.end_id) == (START, END)


@pytest.mark.parametrize('word', ['after'])
def test_parse_accepts_after_as_a_synonym(word):
    assert parse_options(f'{word} {START}')[0].start_id == START


@pytest.mark.parametrize('word', ['to', 'until', 'before'])
def test_parse_accepts_upper_bound_synonyms(word):
    assert parse_options(f'from {START} {word} {END}')[0].end_id == END


@pytest.mark.parametrize('text', ['last 10 --purge', 'last 10 -p', 'purge last 10'])
def test_parse_detects_the_purge_flag(text):
    spec, purge = parse_options(text)
    assert purge is True
    assert spec.limit == 10


def test_parse_without_purge_leaves_it_off():
    assert parse_options('last 10')[1] is False


@pytest.mark.parametrize('text,fragment', [
    ('', 'what to export'),
    ('banana', 'do not understand'),
    ('last', 'How many'),
    ('last x', 'not a number'),
    ('last 0', 'at least one'),
    (f'from {START} sideways {END}', 'Expected'),
    (f'from {START} to', 'needs a message id'),
    ('from 12', 'not a message id'),
])
def test_parse_refuses_bad_input(text, fragment):
    with pytest.raises(ArchiveError, match=fragment):
        parse_options(text)


def test_parse_refuses_a_reversed_range():
    with pytest.raises(ArchiveError, match='swap them'):
        parse_options(f'from {END} to {START}')


def test_parse_refuses_a_count_over_the_limit():
    with pytest.raises(ArchiveError, match='the limit is'):
        parse_options(f'last {archive.max_messages() + 1}')


def test_there_is_no_default_range():
    """An export that guesses its bounds is one that can delete the wrong thing."""
    with pytest.raises(ArchiveError):
        parse_options('   ')


# ---------------------------------------------------------------------------
# missing_permissions
# ---------------------------------------------------------------------------

def test_missing_permissions_reports_only_the_gaps():
    channel = _channel(read_message_history=False)
    gaps = missing_permissions(channel, MagicMock(), {
        'view_channel': 'View Channel',
        'read_message_history': 'Read Message History',
    })
    assert gaps == ['Read Message History']


def test_missing_permissions_is_empty_when_all_granted():
    assert missing_permissions(_channel(), MagicMock(), {'view_channel': 'View Channel'}) == []


# ---------------------------------------------------------------------------
# !archive run — refusals
# ---------------------------------------------------------------------------

async def test_run_without_a_range_refuses(mock_bot):
    cog, ctx = _cog(mock_bot), _ctx(_channel())
    await cog.archive_run.callback(cog, ctx, channel=None, options='')
    assert 'Nothing exported' in _final_embed(ctx).title


async def test_run_with_purge_needs_manage_messages_from_the_caller(mock_bot):
    mock_bot.is_owner = AsyncMock(return_value=False)
    channel = _channel([_message(1001)])
    cog, ctx = _cog(mock_bot), _ctx(channel, can_purge=False)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5 --purge')
    embed = _final_embed(ctx)
    assert 'Nothing exported' in embed.title
    assert 'Manage Messages' in embed.description
    channel.history.assert_not_called()


async def test_run_with_purge_needs_manage_messages_from_the_bot(mock_bot):
    """Checked before the export, not after — nobody should wait out a long
    read only to be told the channel cannot be cleared."""
    channel = _channel([_message(1001)], manage_messages=False)
    cog, ctx = _cog(mock_bot), _ctx(channel)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5 --purge')
    assert 'Manage Messages' in _final_embed(ctx).description
    channel.history.assert_not_called()


async def test_export_without_purge_does_not_need_manage_messages(mock_bot, guild_id):
    channel = _channel([_message(1001)], manage_messages=False)
    cog, ctx = _cog(mock_bot), _ctx(channel, guild_id=guild_id)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5')
    assert archive.get_record(guild_id, channel.id) is not None


async def test_run_without_read_history_permission_refuses(mock_bot):
    channel = _channel(read_message_history=False)
    cog, ctx = _cog(mock_bot), _ctx(channel)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5')
    embed = _final_embed(ctx)
    assert 'Read Message History' in embed.description
    channel.history.assert_not_called()


async def test_run_on_an_empty_range_refuses(mock_bot):
    channel = _channel([])
    cog, ctx = _cog(mock_bot), _ctx(channel)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5')
    assert 'no messages' in _final_embed(ctx).description


async def test_run_refuses_a_range_over_the_message_limit(mock_bot, monkeypatch):
    monkeypatch.setattr('utils.archive.ARCHIVE_MAX_MESSAGES', 2)
    channel = _channel([_message(i) for i in range(1, 6)])
    cog, ctx = _cog(mock_bot), _ctx(channel)
    await cog.archive_run.callback(cog, ctx, channel=channel, options=f'from {START}')
    assert 'the limit is 2' in _final_embed(ctx).description


async def test_run_refuses_when_attachments_exceed_the_byte_limit(mock_bot, monkeypatch):
    monkeypatch.setattr('utils.archive.ARCHIVE_MAX_BUNDLE_MB', 0)
    channel = _channel([_message(1, attachments=[_attachment()])])
    cog, ctx = _cog(mock_bot), _ctx(channel)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5')
    assert 'the limit is 0 MB' in _final_embed(ctx).description


async def test_nothing_is_written_when_a_limit_refuses(mock_bot, monkeypatch, guild_id):
    monkeypatch.setattr('utils.archive.ARCHIVE_MAX_BUNDLE_MB', 0)
    channel = _channel([_message(1, attachments=[_attachment()])])
    cog, ctx = _cog(mock_bot), _ctx(channel, guild_id=guild_id)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5')
    assert list(archive.guild_dir(guild_id).glob('*.zip')) == []
    assert archive.get_record(guild_id, channel.id) is None


# ---------------------------------------------------------------------------
# !archive run — the happy path
# ---------------------------------------------------------------------------

def _bundle_of(guild_id):
    bundles = list(archive.guild_dir(guild_id).glob('*.zip'))
    assert len(bundles) == 1, f'expected one bundle, found {bundles}'
    return bundles[0]


async def _export(mock_bot, messages, guild_id=123456789, **ctx_kwargs):
    channel = _channel(messages)
    cog, ctx = _cog(mock_bot), _ctx(channel, guild_id=guild_id, **ctx_kwargs)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 50')
    return ctx, channel


async def test_export_writes_a_bundle_with_every_part(mock_bot, guild_id):
    await _export(mock_bot, [
        _message(1001, 'first'),
        _message(1002, 'second', attachments=[_attachment('shot.png')]),
        _message(1003, 'third', attachments=[_attachment('notes.pdf')]),
    ], guild_id=guild_id)

    with zipfile.ZipFile(_bundle_of(guild_id)) as zf:
        names = zf.namelist()
        assert 'index.html' in names
        assert 'style.css' in names
        assert 'transcript.pdf' in names
        assert 'transcript.docx' in names
        assert archive.MANIFEST_NAME in names
        assert any(n.startswith('images/') and n.endswith('.png') for n in names)
        assert any(n.startswith('files/') and n.endswith('.pdf') for n in names)


async def test_bundle_documents_are_real_files(mock_bot, guild_id):
    await _export(mock_bot, [_message(1001, 'roll for initiative')], guild_id=guild_id)
    with zipfile.ZipFile(_bundle_of(guild_id)) as zf:
        assert zf.read('transcript.pdf').startswith(b'%PDF')
        assert zf.read('transcript.docx').startswith(b'PK')


async def test_bundle_html_contains_the_messages(mock_bot, guild_id):
    await _export(mock_bot, [_message(1001, 'roll for initiative')], guild_id=guild_id)
    with zipfile.ZipFile(_bundle_of(guild_id)) as zf:
        html = zf.read('index.html').decode('utf-8')
    assert 'roll for initiative' in html
    assert 'general' in html


async def test_manifest_lists_exactly_the_exported_ids(mock_bot, guild_id):
    await _export(mock_bot, [_message(1001), _message(1002), _message(1003)], guild_id=guild_id)
    with zipfile.ZipFile(_bundle_of(guild_id)) as zf:
        manifest = json.loads(zf.read(archive.MANIFEST_NAME))
    assert manifest['message_ids'] == [1001, 1002, 1003]
    assert manifest['message_count'] == 3


async def test_messages_are_stored_oldest_first(mock_bot, guild_id):
    """history() hands back newest-first for a 'last N' range; order must be fixed."""
    await _export(mock_bot, [_message(1001, 'older'), _message(1002, 'newer')], guild_id=guild_id)
    with zipfile.ZipFile(_bundle_of(guild_id)) as zf:
        html = zf.read('index.html').decode('utf-8')
    assert html.index('older') < html.index('newer')


async def test_export_records_what_it_did(mock_bot, guild_id):
    ctx, channel = await _export(mock_bot, [_message(1001)], guild_id=guild_id)
    record = archive.get_record(guild_id, channel.id)
    assert record['message_count'] == 1
    assert record['exported_by_name'] == 'Ivan'
    assert record['bundle'].endswith('.zip')
    assert record['purged_at'] is None


async def test_export_reports_the_saved_path(mock_bot, guild_id):
    ctx, _ = await _export(mock_bot, [_message(1001)], guild_id=guild_id)
    embed = _final_embed(ctx)
    assert 'Exported' in embed.title
    assert 'Saved on the host' in embed.description


async def test_small_bundle_is_attached(mock_bot, guild_id):
    ctx, _ = await _export(mock_bot, [_message(1001)], guild_id=guild_id)
    files = [c.kwargs.get('file') for c in ctx.send.await_args_list]
    assert any(isinstance(f, discord.File) for f in files)


async def test_oversized_bundle_is_not_attached_but_still_saved(mock_bot, guild_id):
    ctx, _ = await _export(mock_bot, [_message(1001)], guild_id=guild_id, filesize_limit=10)
    files = [c.kwargs.get('file') for c in ctx.send.await_args_list]
    assert not any(isinstance(f, discord.File) for f in files)
    assert 'Too big to attach' in _final_embed(ctx).description
    assert _bundle_of(guild_id).exists()


async def test_bundle_is_not_attached_without_attach_files_permission(mock_bot, guild_id):
    channel = _channel([_message(1001)], attach_files=False)
    cog, ctx = _cog(mock_bot), _ctx(channel, guild_id=guild_id)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5')
    files = [c.kwargs.get('file') for c in ctx.send.await_args_list]
    assert not any(isinstance(f, discord.File) for f in files)


async def test_a_failed_attachment_does_not_sink_the_export(mock_bot, guild_id):
    broken = _attachment('gone.png')
    broken.save = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), 'gone'))
    await _export(mock_bot, [
        _message(1001, 'kept', attachments=[broken]),
        _message(1002, 'also kept'),
    ], guild_id=guild_id)

    with zipfile.ZipFile(_bundle_of(guild_id)) as zf:
        manifest = json.loads(zf.read(archive.MANIFEST_NAME))
        assert 'gone.png' not in ' '.join(zf.namelist())
    assert manifest['message_ids'] == [1001, 1002]


async def test_export_defaults_to_the_current_channel(mock_bot, guild_id):
    channel = _channel([_message(1001)])
    cog, ctx = _cog(mock_bot), _ctx(channel, guild_id=guild_id)
    await cog.archive_run.callback(cog, ctx, channel=None, options='last 5')
    assert archive.get_record(guild_id, channel.id) is not None


async def test_an_unexpected_failure_is_reported_not_swallowed(mock_bot, guild_id):
    channel = _channel([_message(1001)])
    channel.history = MagicMock(side_effect=RuntimeError('gateway fell over'))
    cog, ctx = _cog(mock_bot), _ctx(channel, guild_id=guild_id)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5')
    embed = _final_embed(ctx)
    assert 'Export failed' in embed.title
    assert 'gateway fell over' in embed.description


# ---------------------------------------------------------------------------
# !archive status
# ---------------------------------------------------------------------------

async def test_status_with_nothing_exported(mock_bot):
    cog, ctx = _cog(mock_bot), _ctx(_channel())
    await cog.archive_status.callback(cog, ctx, channel=None)
    assert 'Nothing exported yet' in ctx.send.await_args.kwargs['embed'].title


async def test_status_lists_an_export(mock_bot, guild_id):
    channel = _channel([_message(1001)])
    cog, ctx = _cog(mock_bot), _ctx(channel, guild_id=guild_id)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5')
    ctx.send.reset_mock()
    await cog.archive_status.callback(cog, ctx, channel=None)
    description = ctx.send.await_args.kwargs['embed'].description
    assert 'general' in description
    assert 'kept' in description


async def test_status_can_be_narrowed_to_one_channel(mock_bot, guild_id):
    channel = _channel([_message(1001)])
    cog, ctx = _cog(mock_bot), _ctx(channel, guild_id=guild_id)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5')
    other = _channel([], name='other', channel_id=999)
    ctx.send.reset_mock()
    await cog.archive_status.callback(cog, ctx, channel=other)
    assert 'Nothing exported yet' in ctx.send.await_args.kwargs['embed'].title


# ---------------------------------------------------------------------------
# !archive seed
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_seed_delay(monkeypatch):
    monkeypatch.setattr('cogs.archive._SEED_DELAY', 0)


async def test_seed_posts_the_requested_messages(mock_bot):
    channel = _channel()
    cog, ctx = _cog(mock_bot), _ctx(channel)
    await cog.archive_seed.callback(cog, ctx, count=3, channel=channel)
    assert channel.send.await_count == 3
    assert 'Seeded' in _final_embed(ctx).title


async def test_seed_messages_are_numbered_and_marked(mock_bot):
    channel = _channel()
    cog, ctx = _cog(mock_bot), _ctx(channel)
    await cog.archive_seed.callback(cog, ctx, count=2, channel=channel)
    bodies = [c.args[0] for c in channel.send.await_args_list]
    assert all('seed' in b for b in bodies)
    assert '1 of 2' in bodies[0] and '2 of 2' in bodies[1]


@pytest.mark.parametrize('count', [0, -1, 1000])
async def test_seed_refuses_silly_counts(mock_bot, count):
    channel = _channel()
    cog, ctx = _cog(mock_bot), _ctx(channel)
    await cog.archive_seed.callback(cog, ctx, count=count, channel=channel)
    channel.send.assert_not_called()
    assert 'Not seeded' in _final_embed(ctx).title


async def test_seed_refuses_without_send_permission(mock_bot):
    channel = _channel(send_messages=False)
    cog, ctx = _cog(mock_bot), _ctx(channel)
    await cog.archive_seed.callback(cog, ctx, count=2, channel=channel)
    channel.send.assert_not_called()
    assert 'Send Messages' in _final_embed(ctx).description


async def test_seed_defaults_to_the_current_channel(mock_bot):
    channel = _channel()
    cog, ctx = _cog(mock_bot), _ctx(channel)
    await cog.archive_seed.callback(cog, ctx, count=1, channel=None)
    assert channel.send.await_count == 1


# ---------------------------------------------------------------------------
# Clearing a channel
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_delete_delay(monkeypatch):
    monkeypatch.setattr('cogs.archive._SLOW_DELETE_DELAY', 0)


def _recent_id(seconds_ago: int = 60) -> int:
    """A snowflake young enough for Discord's bulk-delete window."""
    millis = (datetime.now(timezone.utc).timestamp() - seconds_ago) * 1000
    return int(millis - archive.DISCORD_EPOCH_MS) << 22


def _decide(monkeypatch, confirmed: bool) -> None:
    """Replace the confirmation with one that has already been answered."""
    from cogs.archive import _PurgeConfirm

    class _Decided(_PurgeConfirm):
        def __init__(self, user_id):
            super().__init__(user_id)
            self.confirmed = confirmed
            self.stop()  # so wait() returns at once

    monkeypatch.setattr('cogs.archive._PurgeConfirm', _Decided)


async def _export_and_purge(mock_bot, messages, guild_id, monkeypatch, confirmed=True):
    _decide(monkeypatch, confirmed)
    channel = _channel(messages)
    cog, ctx = _cog(mock_bot), _ctx(channel, guild_id=guild_id)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 50 --purge')
    return ctx, channel


async def test_purge_deletes_exactly_the_exported_ids(mock_bot, guild_id, monkeypatch):
    ids = [_recent_id(300), _recent_id(200), _recent_id(100)]
    _, channel = await _export_and_purge(
        mock_bot, [_message(i) for i in ids], guild_id, monkeypatch
    )
    channel.delete_messages.assert_awaited_once()
    passed = [obj.id for obj in channel.delete_messages.await_args.args[0]]
    assert passed == ids


async def test_purge_leaves_the_bundle_in_place(mock_bot, guild_id, monkeypatch):
    await _export_and_purge(
        mock_bot, [_message(_recent_id())], guild_id, monkeypatch
    )
    assert _bundle_of(guild_id).exists()


async def test_purge_records_that_it_happened(mock_bot, guild_id, monkeypatch):
    _, channel = await _export_and_purge(
        mock_bot, [_message(_recent_id()), _message(_recent_id(30))], guild_id, monkeypatch
    )
    record = archive.get_record(guild_id, channel.id)
    assert record['purged_at'] is not None
    assert record['purged_count'] == 2


async def test_purge_reports_what_it_deleted(mock_bot, guild_id, monkeypatch):
    ctx, _ = await _export_and_purge(
        mock_bot, [_message(_recent_id())], guild_id, monkeypatch
    )
    titles = [c.kwargs['embed'].title for c in ctx.send.await_args_list if c.kwargs.get('embed')]
    edits = [c.kwargs['embed'].title for c in ctx.progress.edit.await_args_list]
    assert any('Cleared' in t for t in titles + edits)


async def test_declining_deletes_nothing(mock_bot, guild_id, monkeypatch):
    _, channel = await _export_and_purge(
        mock_bot, [_message(_recent_id())], guild_id, monkeypatch, confirmed=False
    )
    channel.delete_messages.assert_not_awaited()
    channel.get_partial_message.assert_not_called()


async def test_declining_says_the_export_is_still_there(mock_bot, guild_id, monkeypatch):
    ctx, _ = await _export_and_purge(
        mock_bot, [_message(_recent_id())], guild_id, monkeypatch, confirmed=False
    )
    titles = [c.kwargs['embed'].title for c in ctx.send.await_args_list if c.kwargs.get('embed')]
    assert any('Channel kept' in t for t in titles)
    assert archive.get_record(guild_id, ctx.channel.id)['purged_at'] is None


async def test_a_confirmation_timeout_deletes_nothing(mock_bot, guild_id, monkeypatch):
    """Fail-safe: the real view is never answered, so the deadline expires."""
    monkeypatch.setattr('cogs.archive.ARCHIVE_CONFIRM_SECS', 0.01)
    channel = _channel([_message(_recent_id())])
    cog, ctx = _cog(mock_bot), _ctx(channel, guild_id=guild_id)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5 --purge')
    channel.delete_messages.assert_not_awaited()
    assert archive.get_record(guild_id, channel.id)['purged_at'] is None


async def test_old_messages_are_deleted_one_at_a_time(mock_bot, guild_id, monkeypatch):
    """Discord refuses to bulk-delete anything over two weeks old."""
    old = [1001, 1002]  # tiny snowflakes are, by definition, from 2015
    _, channel = await _export_and_purge(
        mock_bot, [_message(i) for i in old], guild_id, monkeypatch
    )
    channel.delete_messages.assert_not_awaited()
    assert [c.args[0] for c in channel.get_partial_message.call_args_list] == old


async def test_a_mixed_range_uses_both_paths(mock_bot, guild_id, monkeypatch):
    recent, old = _recent_id(), 1001
    _, channel = await _export_and_purge(
        mock_bot, [_message(old), _message(recent)], guild_id, monkeypatch
    )
    assert [o.id for o in channel.delete_messages.await_args.args[0]] == [recent]
    assert [c.args[0] for c in channel.get_partial_message.call_args_list] == [old]


async def test_already_deleted_messages_count_as_done(mock_bot, guild_id, monkeypatch):
    channel = _channel([_message(_recent_id())])
    channel.delete_messages = AsyncMock(
        side_effect=discord.NotFound(MagicMock(status=404), 'gone')
    )
    _decide(monkeypatch, True)
    cog, ctx = _cog(mock_bot), _ctx(channel, guild_id=guild_id)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5 --purge')
    assert archive.get_record(guild_id, channel.id)['purged_count'] == 1


async def test_a_failed_delete_is_reported_as_partial(mock_bot, guild_id, monkeypatch):
    channel = _channel([_message(_recent_id())])
    channel.delete_messages = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(status=500), 'boom')
    )
    _decide(monkeypatch, True)
    cog, ctx = _cog(mock_bot), _ctx(channel, guild_id=guild_id)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5 --purge')
    edits = [c.kwargs['embed'] for c in ctx.progress.edit.await_args_list]
    titles = [c.kwargs['embed'].title for c in ctx.send.await_args_list if c.kwargs.get('embed')]
    assert any('Partly cleared' in e.title for e in edits) or any('Partly' in t for t in titles)


# --- the interlock ---------------------------------------------------------

async def test_purge_refuses_when_the_bundle_is_gone(mock_bot, tmp_path):
    """The backup on disk is the only thing that authorises a deletion."""
    channel = _channel()
    cog, ctx = _cog(mock_bot), _ctx(channel)
    with pytest.raises(ArchiveError, match='is gone'):
        await cog._purge(ctx, channel, tmp_path / 'never-written.zip')
    channel.delete_messages.assert_not_awaited()


async def test_purge_refuses_when_the_bundle_is_unreadable(mock_bot, tmp_path):
    broken = tmp_path / 'broken.zip'
    broken.write_text('not a zip', encoding='utf-8')
    channel = _channel()
    cog, ctx = _cog(mock_bot), _ctx(channel)
    with pytest.raises(ArchiveError, match='could not be read'):
        await cog._purge(ctx, channel, broken)
    channel.delete_messages.assert_not_awaited()


async def test_purge_reads_its_targets_from_the_bundle_not_memory(mock_bot, guild_id,
                                                                  monkeypatch):
    """Rewriting the manifest changes what gets deleted — proving the bundle,
    not the in-memory export, is the authority."""
    _decide(monkeypatch, True)
    channel = _channel([_message(_recent_id())])
    cog, ctx = _cog(mock_bot), _ctx(channel, guild_id=guild_id)
    await cog.archive_run.callback(cog, ctx, channel=channel, options='last 5')

    bundle = _bundle_of(guild_id)
    substitute = _recent_id(500)
    monkeypatch.setattr(
        'utils.archive.read_manifest',
        lambda _path: {'message_ids': [substitute]},
    )
    await cog._purge(ctx, channel, bundle)
    assert [o.id for o in channel.delete_messages.await_args.args[0]] == [substitute]


async def test_an_empty_manifest_deletes_nothing(mock_bot, tmp_path, monkeypatch):
    channel = _channel()
    cog, ctx = _cog(mock_bot), _ctx(channel)
    monkeypatch.setattr('utils.archive.read_manifest', lambda _p: {'message_ids': []})
    await cog._purge(ctx, channel, tmp_path / 'whatever.zip')
    channel.delete_messages.assert_not_awaited()


# --- the confirmation view -------------------------------------------------

async def test_only_the_invoker_can_confirm():
    from cogs.archive import _PurgeConfirm

    view = _PurgeConfirm(42)
    outsider = MagicMock()
    outsider.user.id = 99
    outsider.response.send_message = AsyncMock()
    assert await view.interaction_check(outsider) is False
    outsider.response.send_message.assert_awaited_once()


async def test_the_invoker_passes_the_check():
    from cogs.archive import _PurgeConfirm

    view = _PurgeConfirm(42)
    owner = MagicMock()
    owner.user.id = 42
    assert await view.interaction_check(owner) is True


def test_the_view_starts_unconfirmed():
    """Nothing is deleted unless somebody actively says so."""
    from cogs.archive import _PurgeConfirm

    assert _PurgeConfirm(42).confirmed is False
