from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import time
import zipfile
from pathlib import Path

import discord
from discord.ext import commands

from utils import archive
from utils import transcript as render
from utils.archive import (
    ArchiveError,
    ArchivedAttachment,
    ArchivedMessage,
    RangeSpec,
    Transcript,
)
from utils.config import ARCHIVE_PROGRESS_EVERY, PREFIX
from utils.message import MessageWriter

log = logging.getLogger(__name__)

_PURGE_WORDS = {'--purge', '-p', 'purge'}
_FROM_WORDS = {'from', 'after'}
_TO_WORDS = {'to', 'until', 'before'}

# A dev aid, not a feature — keep it small enough that a slip cannot flood a
# channel, and slow enough not to trip the per-channel send rate limit.
_MAX_SEED = 100
_SEED_DELAY = 0.6

_USAGE = (
    f'Give an explicit range:\n'
    f'`{PREFIX}archive run last 500`\n'
    f'`{PREFIX}archive run from <message_id>`\n'
    f'`{PREFIX}archive run from <message_id> to <message_id>`\n'
    f'Add a channel first to export another one: '
    f'`{PREFIX}archive run #general last 200`'
)


def _snowflake(token: str) -> int:
    """Parse a message id, rejecting anything that cannot be one."""
    if not token.isdigit() or not 15 <= len(token) <= 20:
        raise ArchiveError(f'`{token}` is not a message id. Right-click a message → Copy Message ID.')
    return int(token)


def parse_options(text: str) -> tuple[RangeSpec, bool]:
    """Split the options of !archive run into (range, purge).

    There is deliberately no default range — an export that guesses its own
    bounds is one that can delete the wrong thing.
    """
    tokens = text.replace(',', ' ').split()
    purge = False
    kept: list[str] = []
    for token in tokens:
        if token.lower() in _PURGE_WORDS:
            purge = True
        else:
            kept.append(token.lower())

    if not kept:
        raise ArchiveError(f'I need to know what to export. {_USAGE}')

    head = kept[0]

    if head == 'last':
        if len(kept) < 2:
            raise ArchiveError(f'How many messages? `{PREFIX}archive run last 500`')
        if not kept[1].isdigit():
            raise ArchiveError(f'`{kept[1]}` is not a number of messages.')
        count = int(kept[1])
        if count < 1:
            raise ArchiveError('Export at least one message.')
        archive.check_message_count(count)
        return RangeSpec(limit=count), purge

    if head in _FROM_WORDS:
        if len(kept) < 2:
            raise ArchiveError(f'From which message? `{PREFIX}archive run from <message_id>`')
        start = _snowflake(kept[1])
        end = None
        if len(kept) > 2:
            if kept[2] not in _TO_WORDS:
                raise ArchiveError(f'Expected `to <message_id>` after the first id, got `{kept[2]}`.')
            if len(kept) < 4:
                raise ArchiveError('`to` needs a message id after it.')
            end = _snowflake(kept[3])
            if end < start:
                raise ArchiveError('The second message id is older than the first — swap them.')
        return RangeSpec(start_id=start, end_id=end), purge

    raise ArchiveError(f'I do not understand `{head}`. {_USAGE}')


def missing_permissions(channel: discord.abc.GuildChannel, me: discord.Member,
                        needed: dict[str, str]) -> list[str]:
    """Which of the needed permissions the bot lacks in this channel.

    `needed` maps attribute name to the human label shown to the user.
    """
    perms = channel.permissions_for(me)
    return [label for attr, label in needed.items() if not getattr(perms, attr, False)]


def _to_archived(message: discord.Message) -> tuple[ArchivedMessage, list[discord.Attachment]]:
    """Flatten a Discord message, and hand back its attachments to download."""
    attachments = []
    for index, att in enumerate(message.attachments):
        attachments.append(ArchivedAttachment(
            filename=att.filename,
            stored_as=archive.stored_name(message.id, index, att.filename),
            size=att.size,
            content_type=att.content_type or '',
        ))
    archived = ArchivedMessage(
        id=message.id,
        author_id=message.author.id,
        author_name=message.author.display_name,
        created_at=message.created_at,
        content=message.content or '',
        edited=message.edited_at is not None,
        attachments=attachments,
    )
    return archived, list(message.attachments)


def _build_bundle(dest: Path, staging: Path, transcript: Transcript, manifest: dict) -> None:
    """Render every format and zip it with the staged attachments.

    All of this blocks — rendering a PDF and recompressing images are both CPU
    work — so callers hand it to an executor rather than running it on the
    event loop.

    The zip is written to a .part file and moved into place, so a crash cannot
    leave a half-written bundle that a later purge might trust.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f'{dest.name}.part')
    try:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('index.html', render.render_html(transcript))
            zf.writestr('style.css', render.STYLE_CSS)
            zf.writestr('transcript.pdf', render.render_pdf(transcript, root=staging))
            zf.writestr('transcript.docx', render.render_docx(transcript, root=staging))
            zf.writestr(archive.MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False))
            for path in sorted(staging.rglob('*')):
                if path.is_file():
                    zf.write(path, path.relative_to(staging).as_posix())
        tmp.replace(dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class ArchiveCog(commands.Cog, name='Archive'):
    """Export a channel to a readable bundle, and clear what was exported."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        # Exports expose a channel's whole history, so the bar is Manage Server.
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        if isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.manage_guild:
            return True
        return await self.bot.is_owner(ctx.author)

    @commands.hybrid_group(name='archive', invoke_without_command=True)
    async def archive_group(self, ctx: commands.Context) -> None:
        """Export a channel's messages, images and files to a bundle."""
        await self._status(ctx, None)

    # --- status ------------------------------------------------------------

    @archive_group.command(name='status')
    async def archive_status(self, ctx: commands.Context,
                             channel: discord.TextChannel | None = None) -> None:
        """Show what has been exported from this server."""
        await self._status(ctx, channel)

    async def _status(self, ctx: commands.Context,
                      channel: discord.TextChannel | None) -> None:
        records = archive.all_records(ctx.guild.id)
        if channel is not None:
            record = records.get(str(channel.id))
            records = {str(channel.id): record} if record else {}
        await ctx.send(embed=MessageWriter.archive_status(records, PREFIX))

    # --- seed --------------------------------------------------------------

    @archive_group.command(name='seed')
    @commands.is_owner()
    async def archive_seed(self, ctx: commands.Context, count: int,
                           channel: discord.TextChannel | None = None) -> None:
        """Owner only — post numbered test messages so an export can be tried safely."""
        target = channel or ctx.channel
        if count < 1 or count > _MAX_SEED:
            await ctx.send(embed=MessageWriter.error(
                'Not seeded', f'Pick between 1 and {_MAX_SEED} messages.'
            ))
            return

        gaps = missing_permissions(target, ctx.guild.me, {'send_messages': 'Send Messages'})
        if gaps:
            await ctx.send(embed=MessageWriter.error(
                'Not seeded', f'I need {", ".join(gaps)} in {target.mention}.'
            ))
            return

        stamp = int(time.time())
        for index in range(1, count + 1):
            await target.send(f'[seed {stamp}] test message {index} of {count}')
            await asyncio.sleep(_SEED_DELAY)
        log.info('Seeded %s messages into %s by %s', count, target.id, ctx.author)
        await ctx.send(embed=MessageWriter.success(
            'Seeded', f'Posted {count} test messages in {target.mention}.'
        ))

    # --- run ---------------------------------------------------------------

    @archive_group.command(name='run')
    async def archive_run(self, ctx: commands.Context,
                          channel: discord.TextChannel | None = None,
                          *, options: str = '') -> None:
        """Export a range of messages. Needs an explicit range, e.g. last 500."""
        target = channel or ctx.channel

        try:
            spec, purge = parse_options(options)
        except ArchiveError as exc:
            await ctx.send(embed=MessageWriter.error('Nothing exported', str(exc)))
            return

        if purge:
            await ctx.send(embed=MessageWriter.error(
                'Nothing exported',
                'Deleting messages is not built yet — run the export without `--purge`.',
            ))
            return

        gaps = missing_permissions(target, ctx.guild.me, {
            'view_channel': 'View Channel',
            'read_message_history': 'Read Message History',
        })
        if gaps:
            await ctx.send(embed=MessageWriter.error(
                'Nothing exported',
                f'I need {", ".join(gaps)} in {target.mention} to read its history.',
            ))
            return

        progress = await ctx.send(embed=MessageWriter.info(
            'Exporting', f'Reading {spec.describe()} from {target.mention}…'
        ))

        try:
            await self._export(ctx, target, spec, progress)
        except ArchiveError as exc:
            await progress.edit(embed=MessageWriter.error('Nothing exported', str(exc)))
        except discord.Forbidden:
            await progress.edit(embed=MessageWriter.error(
                'Nothing exported', f'Discord refused me access to {target.mention}.'
            ))
        except Exception as exc:
            log.error('Export of channel %s failed: %s', target.id, exc, exc_info=exc)
            await progress.edit(embed=MessageWriter.error(
                'Export failed', f'{type(exc).__name__}: {exc}'
            ))

    async def _export(self, ctx: commands.Context, target: discord.TextChannel,
                      spec: RangeSpec, progress: discord.Message) -> None:
        collected: list[tuple[ArchivedMessage, list[discord.Attachment]]] = []

        # Snowflakes are unique integers, so offsetting by one turns the user's
        # inclusive bounds into Discord's exclusive ones without risk.
        if spec.limit is not None:
            history = target.history(limit=spec.limit, oldest_first=False)
        else:
            history = target.history(
                limit=None,
                after=discord.Object(id=spec.start_id - 1),
                before=discord.Object(id=spec.end_id + 1) if spec.end_id else None,
                oldest_first=True,
            )

        async for message in history:
            collected.append(_to_archived(message))
            if len(collected) % ARCHIVE_PROGRESS_EVERY == 0:
                await progress.edit(embed=MessageWriter.info(
                    'Exporting', f'Read {len(collected)} messages from {target.mention}…'
                ))
            if len(collected) > archive.max_messages():
                # Stop reading rather than walk a whole channel to then refuse.
                archive.check_message_count(len(collected))

        if spec.limit is not None:
            collected.reverse()  # history() gave newest first

        if not collected:
            raise ArchiveError(f'There are no messages in {spec.describe()}.')

        archive.check_message_count(len(collected))
        total_bytes = sum(att.size for _, atts in collected for att in atts)
        archive.check_attachment_bytes(total_bytes)

        transcript = Transcript(
            guild_name=ctx.guild.name,
            channel_name=target.name,
            messages=[archived for archived, _ in collected],
        )

        with tempfile.TemporaryDirectory(prefix='chronicler-export-') as tmpdir:
            staging = Path(tmpdir)
            await self._download(collected, staging, progress, target)

            manifest = archive.build_manifest(
                transcript,
                guild_id=ctx.guild.id,
                channel_id=target.id,
                exported_by=ctx.author.id,
                exported_by_name=ctx.author.display_name,
            )
            dest = archive.guild_dir(ctx.guild.id) / archive.bundle_name(
                target.name, transcript.generated_at
            )
            await progress.edit(embed=MessageWriter.info(
                'Exporting', f'Rendering {len(collected)} messages…'
            ))
            await asyncio.get_running_loop().run_in_executor(
                None, _build_bundle, dest, staging, transcript, manifest
            )

        archive.record_export(ctx.guild.id, target.id, manifest, dest)
        log.info(
            'Exported %s messages from channel %s to %s (%s bytes) for %s',
            manifest['message_count'], target.id, dest.name,
            dest.stat().st_size, ctx.author,
        )
        await self._deliver(ctx, progress, manifest, dest)

    async def _download(self, collected, staging: Path,
                        progress: discord.Message, target: discord.TextChannel) -> None:
        """Save every attachment into the staging tree under its bundle name."""
        images = staging / archive.IMAGES_DIR
        files = staging / archive.FILES_DIR
        images.mkdir(parents=True, exist_ok=True)
        files.mkdir(parents=True, exist_ok=True)

        done = 0
        for archived, raw in collected:
            for meta, attachment in zip(archived.attachments, raw):
                folder = images if meta.is_image else files
                dest = folder / meta.stored_as
                try:
                    await attachment.save(dest)
                except (discord.HTTPException, discord.NotFound, OSError) as exc:
                    # A single unreachable attachment must not sink the export,
                    # but the message still counts as exported, so say so.
                    dest.unlink(missing_ok=True)
                    log.warning('Attachment %s could not be saved: %s', meta.filename, exc)
                done += 1
                if done % ARCHIVE_PROGRESS_EVERY == 0:
                    await progress.edit(embed=MessageWriter.info(
                        'Exporting', f'Saved {done} attachments from {target.mention}…'
                    ))

    async def _deliver(self, ctx: commands.Context, progress: discord.Message,
                       manifest: dict, dest: Path) -> None:
        """Always report the saved path; attach the bundle when it fits."""
        size = dest.stat().st_size
        limit = ctx.guild.filesize_limit
        can_attach = not missing_permissions(
            ctx.channel, ctx.guild.me, {'attach_files': 'Attach Files'}
        )
        uploaded = size <= limit and can_attach

        embed = MessageWriter.archive_card(manifest, dest, uploaded=uploaded, limit=limit)
        await progress.edit(embed=embed)
        if uploaded:
            await ctx.send(file=discord.File(dest, filename=dest.name))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ArchiveCog(bot))
