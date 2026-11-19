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

    granted = {
        'view_channel': True, 'read_message_history': True,
        'send_messages': True, 'attach_files': True,
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


def _ctx(channel, guild_id=123456789, filesize_limit=8 * 1024 * 1024):
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = guild_id
    ctx.guild.name = 'The Table'
    ctx.guild.me = MagicMock()
    ctx.guild.filesize_limit = filesize_limit
    ctx.channel = channel
    ctx.author = MagicMock()
    ctx.author.id = 42
    ctx.author.display_name = 'Ivan'
    progress = MagicMock()
    progress.edit = AsyncMock()
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


async def test_run_with_purge_is_refused_until_it_is_built(mock_bot):
    cog, ctx = _cog(mock_bot), _ctx(_channel())
    await cog.archive_run.callback(cog, ctx, channel=None, options='last 5 --purge')
    embed = _final_embed(ctx)
    assert 'Nothing exported' in embed.title
    assert 'not built yet' in embed.description


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
        assert archive.MANIFEST_NAME in names
        assert any(n.startswith('images/') and n.endswith('.png') for n in names)
        assert any(n.startswith('files/') and n.endswith('.pdf') for n in names)


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
