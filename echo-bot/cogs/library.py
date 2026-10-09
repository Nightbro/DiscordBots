from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from utils import library
from utils.audio import AUDIO_EXTS, AudioFileManager
from utils.i18n import t
from utils.message import MessageWriter
from utils.notifier import Notifier
from utils.voice import VoiceStreamer

log = logging.getLogger(__name__)

_PAGE_SIZE = 10


def _line(index: int, meta: dict) -> str:
    return (
        f'`{index:>2}.` **{meta["title"]}** · {library.format_duration(meta.get("duration"))}'
        f' · {meta.get("added_by_name", "?")}'
    )


def _list_embed(guild_id: int, page: int) -> tuple[discord.Embed, list[tuple[str, dict]]]:
    """Build the library page embed and return the tracks shown on it."""
    tracks = library.track_list(guild_id)
    pages = max(1, -(-len(tracks) // _PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    shown = tracks[page * _PAGE_SIZE:(page + 1) * _PAGE_SIZE]
    if not tracks:
        return MessageWriter.info(t('library.title', guild_id), t('library.empty', guild_id)), []
    used_mb = library.total_size(guild_id) / 1024 / 1024
    body = '\n'.join(
        _line(page * _PAGE_SIZE + i + 1, meta) for i, (_, meta) in enumerate(shown)
    )
    footer = t(
        'library.footer', guild_id,
        page=page + 1, pages=pages, count=len(tracks),
        max=library.MAX_TRACKS, used=f'{used_mb:.0f}', limit=library.MAX_TOTAL_MB,
    )
    embed = MessageWriter.info(t('library.title', guild_id), f'{body}\n\n{footer}')
    return embed, shown


class _LibraryView(discord.ui.View):
    """Page buttons plus a dropdown that queues the picked track."""

    def __init__(self, cog: LibraryCog, guild_id: int, user_id: int, page: int = 0) -> None:
        super().__init__(timeout=180.0)
        self._cog = cog
        self._guild_id = guild_id
        self._user_id = user_id
        self._page = page
        self._build()

    def _build(self) -> None:
        self.clear_items()
        _, shown = _list_embed(self._guild_id, self._page)
        tracks = library.track_list(self._guild_id)
        pages = max(1, -(-len(tracks) // _PAGE_SIZE))
        if shown:
            options = [
                discord.SelectOption(
                    label=meta['title'][:100],
                    value=slug,
                    description=library.format_duration(meta.get('duration')),
                )
                for slug, meta in shown
            ]
            select = discord.ui.Select(
                placeholder=t('library.pick', self._guild_id), options=options,
            )
            select.callback = self._on_pick
            self.add_item(select)
        if pages > 1:
            prev_button = discord.ui.Button(label='◀', disabled=self._page == 0)
            next_button = discord.ui.Button(label='▶', disabled=self._page >= pages - 1)
            prev_button.callback = self._on_prev
            next_button.callback = self._on_next
            self.add_item(prev_button)
            self.add_item(next_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self._user_id:
            return True
        await interaction.response.send_message(
            t('library.not_yours', self._guild_id), ephemeral=True,
        )
        return False

    async def _turn_page(self, interaction: discord.Interaction, delta: int) -> None:
        self._page += delta
        self._build()
        embed, _ = _list_embed(self._guild_id, self._page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        await self._turn_page(interaction, -1)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        await self._turn_page(interaction, 1)

    async def _on_pick(self, interaction: discord.Interaction) -> None:
        slug = interaction.data['values'][0]  # type: ignore[index]
        meta = library.get_track(self._guild_id, slug)
        if meta is None:
            await interaction.response.send_message(
                t('library.not_found', self._guild_id, query=slug), ephemeral=True,
            )
            return
        await interaction.response.defer()
        await self._cog.queue_track(interaction, self._guild_id, slug)


class LibraryCog(commands.Cog, name='Library'):
    """Per-server library of uploaded tracks: !save to add, !library to browse and play."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _notifier(self, ctx) -> Notifier:
        return Notifier(self.bot, ctx.guild.id)

    # -----------------------------------------------------------------------
    # Playback
    # -----------------------------------------------------------------------

    async def play_slug(self, ctx, slug: str) -> bool:
        """Queue a library track for a prefix/slash invocation. Returns False if it failed."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        track = library.to_track(gid, slug)
        if track is None:
            await notifier.error(ctx, t('library.file_missing', gid))
            return False
        if ctx.author.voice is None:
            await notifier.error(ctx, t('common.error_no_voice', gid))
            return False
        track.requester = ctx.author
        streamer = VoiceStreamer(self.bot, gid)
        await streamer.join(ctx.author.voice.channel)
        await streamer.play(track)
        library.bump_plays(gid, slug)
        await notifier.track_card(
            ctx, MessageWriter.track_card(track, guild_id=gid), title=track.title,
        )
        return True

    async def queue_track(self, interaction: discord.Interaction, guild_id: int, slug: str) -> None:
        """Queue a track picked from the dropdown."""
        track = library.to_track(guild_id, slug)
        member = interaction.user
        if track is None:
            await interaction.followup.send(t('library.file_missing', guild_id), ephemeral=True)
            return
        if not isinstance(member, discord.Member) or member.voice is None:
            await interaction.followup.send(
                t('common.error_no_voice', guild_id), ephemeral=True,
            )
            return
        track.requester = member
        streamer = VoiceStreamer(self.bot, guild_id)
        await streamer.join(member.voice.channel)
        await streamer.play(track)
        library.bump_plays(guild_id, slug)
        await interaction.followup.send(
            embed=MessageWriter.track_card(track, guild_id=guild_id),
        )

    # -----------------------------------------------------------------------
    # Commands
    # -----------------------------------------------------------------------

    @commands.command(name='save', aliases=['upload'])
    async def save(self, ctx: commands.Context, *, name: str = '') -> None:
        """Save an attached audio file to this server's library."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)

        attachment = await self._find_attachment(ctx)
        if attachment is None:
            await notifier.error(
                ctx, t('library.no_attachment', gid),
                t('library.no_attachment_hint', gid, formats=', '.join(sorted(AUDIO_EXTS))),
            )
            return
        if not AudioFileManager.is_valid_audio(attachment.filename):
            await notifier.error(
                ctx, t('library.bad_format', gid),
                t('library.bad_format_hint', gid, formats=', '.join(sorted(AUDIO_EXTS))),
            )
            return

        title = (name or Path(attachment.filename).stem).strip()
        slug = library.slugify(title)
        if library.get_track(gid, slug):
            await notifier.error(ctx, t('library.name_taken', gid, title=title))
            return
        try:
            library.check_quota(gid, attachment.size)
        except library.LibraryError as exc:
            await notifier.error(ctx, self._quota_message(gid, exc))
            return

        dest = library.guild_dir(gid) / f'{slug}{Path(attachment.filename).suffix.lower()}'
        try:
            await attachment.save(dest)
            duration = await library.probe_duration(dest)
            library.add_track(
                gid, title, dest,
                duration=duration,
                added_by=ctx.author.id,
                added_by_name=ctx.author.display_name,
            )
        except library.LibraryError as exc:
            dest.unlink(missing_ok=True)
            await notifier.error(ctx, self._quota_message(gid, exc))
            return
        except Exception as exc:
            dest.unlink(missing_ok=True)
            log.error('Library save failed for "%s": %s', title, exc, exc_info=exc)
            await notifier.error(ctx, t('library.save_failed', gid), str(exc))
            return

        log.info('Library: %s added "%s" in guild %s', ctx.author, title, gid)
        index = next(
            (i for i, (s, _) in enumerate(library.track_list(gid), 1) if s == slug), 0,
        )
        await notifier.success(
            ctx, t('library.saved', gid, title=title),
            t('library.saved_hint', gid, title=title, index=index,
              size=f'{attachment.size / 1024 / 1024:.1f}',
              duration=library.format_duration(duration)),
        )

    @commands.group(name='library', aliases=['lib'], invoke_without_command=True)
    async def library_cmd(self, ctx: commands.Context, *, query: str = '') -> None:
        """Browse this server's library; with a name or #N, play that track."""
        gid = ctx.guild.id
        if query:
            match = library.resolve(gid, query)
            if match is None:
                await self._notifier(ctx).error(ctx, t('library.not_found', gid, query=query))
                return
            await self.play_slug(ctx, match[0])
            return
        embed, _ = _list_embed(gid, 0)
        view = _LibraryView(self, gid, ctx.author.id)
        await ctx.send(embed=embed, view=view if view.children else None)

    @library_cmd.command(name='play')
    async def library_play(self, ctx: commands.Context, *, query: str) -> None:
        """Play a library track by name or #N."""
        gid = ctx.guild.id
        match = library.resolve(gid, query)
        if match is None:
            await self._notifier(ctx).error(ctx, t('library.not_found', gid, query=query))
            return
        await self.play_slug(ctx, match[0])

    @library_cmd.command(name='remove', aliases=['delete'])
    async def library_remove(self, ctx: commands.Context, *, query: str) -> None:
        """Remove a track from the library by name or #N."""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        match = library.resolve(gid, query)
        if match is None:
            await notifier.error(ctx, t('library.not_found', gid, query=query))
            return
        slug, meta = match
        library.remove_track(gid, slug)
        log.info('Library: %s removed "%s" in guild %s', ctx.author, meta['title'], gid)
        await notifier.success(ctx, t('library.removed', gid, title=meta['title']))

    @library_cmd.command(name='rename')
    async def library_rename(self, ctx: commands.Context, query: str, *, new_title: str) -> None:
        """Rename a library track: !lib rename #3 New Name"""
        gid = ctx.guild.id
        notifier = self._notifier(ctx)
        match = library.resolve(gid, query)
        if match is None:
            await notifier.error(ctx, t('library.not_found', gid, query=query))
            return
        slug, meta = match
        old_title = meta['title']
        try:
            library.rename_track(gid, slug, new_title.strip())
        except library.LibraryError:
            await notifier.error(ctx, t('library.name_taken', gid, title=new_title))
            return
        await notifier.success(
            ctx, t('library.renamed', gid, old=old_title, new=new_title.strip()),
        )

    @library_cmd.command(name='info')
    async def library_info(self, ctx: commands.Context, *, query: str) -> None:
        """Show details for one library track."""
        gid = ctx.guild.id
        match = library.resolve(gid, query)
        if match is None:
            await self._notifier(ctx).error(ctx, t('library.not_found', gid, query=query))
            return
        slug, meta = match
        await ctx.send(embed=MessageWriter.info(meta['title'], t(
            'library.info', gid,
            duration=library.format_duration(meta.get('duration')),
            size=f'{meta.get("size", 0) / 1024 / 1024:.1f}',
            added_by=meta.get('added_by_name', '?'),
            added_at=meta.get('added_at', '?'),
            plays=meta.get('plays', 0),
            slug=slug,
        )))

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    async def _find_attachment(ctx: commands.Context) -> discord.Attachment | None:
        """The file on this message, or on the message it replies to."""
        if ctx.message.attachments:
            return ctx.message.attachments[0]
        ref = ctx.message.reference
        if ref is None:
            return None
        replied = ref.resolved
        if replied is None and ref.message_id:
            try:
                replied = await ctx.channel.fetch_message(ref.message_id)
            except discord.HTTPException:
                return None
        if isinstance(replied, discord.Message) and replied.attachments:
            return replied.attachments[0]
        return None

    @staticmethod
    def _quota_message(guild_id: int, exc: library.LibraryError) -> str:
        reason, _, value = str(exc).partition(':')
        if reason == 'track_limit':
            return t('library.limit_tracks', guild_id, max=value)
        if reason == 'size_limit':
            return t('library.limit_size', guild_id, limit=value)
        if reason == 'name_taken':
            return t('library.name_taken', guild_id, title=value)
        return t('library.save_failed', guild_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LibraryCog(bot))
