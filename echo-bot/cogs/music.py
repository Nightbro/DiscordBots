from __future__ import annotations

import random
from typing import Any

import discord
from discord.ext import commands

from utils.config import EMOJI_LOADING, EMOJI_MUSIC, MAX_QUEUE
from utils.downloader import Downloader
from utils.guild_state import GuildState, Track
from utils.i18n import t
from utils.message import MessageWriter
from utils.persistence import PlaylistConfig
from utils.voice import VoiceStreamer

_PAGE_SIZE = 10


# ---------------------------------------------------------------------------
# Track serialization helpers
# ---------------------------------------------------------------------------

def _track_to_dict(track: Track) -> dict[str, Any]:
    return {
        'title': track.title,
        'url': track.url,
        'duration': track.duration,
        'source_id': track.source_id,
    }


def _dict_to_track(data: dict[str, Any]) -> Track:
    return Track(
        title=data['title'],
        url=data['url'],
        duration=data.get('duration'),
        source_id=data.get('source_id'),
    )


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class MusicCog(commands.Cog, name='Music'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _state(self, ctx) -> GuildState:
        return self.bot.get_guild_state(ctx.guild.id)

    def _streamer(self, ctx) -> VoiceStreamer:
        return VoiceStreamer(self.bot, ctx.guild.id)

    async def _ensure_voice(self, ctx) -> tuple[VoiceStreamer | None, bool]:
        if ctx.author.voice is None:
            await ctx.send(embed=MessageWriter.error(t('common.error_no_voice', ctx.guild.id)))
            return None, False
        streamer = self._streamer(ctx)
        just_connected = self._state(ctx).voice_client is None
        await streamer.join(ctx.author.voice.channel)
        return streamer, just_connected

    # -----------------------------------------------------------------------
    # Playback
    # -----------------------------------------------------------------------

    @commands.hybrid_command(name='play', aliases=['p'])
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        """Add a track to the queue and start playback."""
        gid = ctx.guild.id
        streamer, _ = await self._ensure_voice(ctx)
        if streamer is None:
            return

        loading = await ctx.send(embed=MessageWriter.info(t('music.resolving', gid)))

        try:
            track = await Downloader.resolve(query)
            track.requester = ctx.author
        except Exception as exc:
            await loading.edit(embed=MessageWriter.error(t('music.error_resolve', gid), str(exc)))
            return

        try:
            await streamer.play(track)
        except ValueError as exc:
            await loading.edit(embed=MessageWriter.error(str(exc)))
            return

        await loading.edit(embed=MessageWriter.track_card(track, guild_id=gid))

    @commands.hybrid_command(name='skip', aliases=['s'])
    async def skip(self, ctx: commands.Context) -> None:
        """Skip the current track."""
        gid = ctx.guild.id
        skipped = await self._streamer(ctx).skip()
        if skipped:
            await ctx.send(embed=MessageWriter.success(t('music.skip.skipped', gid, title=skipped.title)))
        else:
            await ctx.send(embed=MessageWriter.error(t('music.skip.nothing', gid)))

    @commands.hybrid_command(name='pause')
    async def pause(self, ctx: commands.Context) -> None:
        """Pause playback."""
        await self._streamer(ctx).pause()
        await ctx.send(embed=MessageWriter.success(t('music.paused', ctx.guild.id)))

    @commands.hybrid_command(name='resume', aliases=['unpause'])
    async def resume(self, ctx: commands.Context) -> None:
        """Resume playback."""
        await self._streamer(ctx).resume()
        await ctx.send(embed=MessageWriter.success(t('music.resumed', ctx.guild.id)))

    @commands.hybrid_command(name='stop')
    async def stop(self, ctx: commands.Context) -> None:
        """Stop playback and clear the queue."""
        await self._streamer(ctx).stop()
        await ctx.send(embed=MessageWriter.success(t('music.stopped', ctx.guild.id)))

    @commands.hybrid_command(name='nowplaying', aliases=['np'])
    async def now_playing(self, ctx: commands.Context) -> None:
        """Show the currently playing track."""
        gid = ctx.guild.id
        track = self._state(ctx).current_track
        if track:
            await ctx.send(embed=MessageWriter.track_card(track, guild_id=gid))
        else:
            await ctx.send(embed=MessageWriter.info(t('music.nothing_playing', gid)))

    # -----------------------------------------------------------------------
    # Queue
    # -----------------------------------------------------------------------

    @commands.hybrid_command(name='queue', aliases=['q'])
    async def queue(self, ctx: commands.Context, page: int = 1) -> None:
        """Show the playback queue."""
        gid = ctx.guild.id
        state = self._state(ctx)
        tracks = list(state.queue)
        total = len(tracks)
        total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
        page = max(1, min(page, total_pages))
        chunk = tracks[(page - 1) * _PAGE_SIZE: page * _PAGE_SIZE]

        embed = MessageWriter.queue_page(chunk, page, total_pages, guild_id=gid)

        if state.current_track:
            tr = state.current_track
            dur = ''
            if tr.duration is not None:
                m, s = divmod(tr.duration, 60)
                dur = f' `{m}:{s:02d}`'
            now_line = t('music.queue.now_playing', gid, emoji=EMOJI_MUSIC, title=tr.title, dur=dur) + '\n\n'
            embed.description = now_line + (embed.description or '')

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='clear')
    async def clear(self, ctx: commands.Context) -> None:
        """Clear the queue (keeps current track playing)."""
        self._state(ctx).queue.clear()
        await ctx.send(embed=MessageWriter.success(t('music.queue.cleared', ctx.guild.id)))

    @commands.hybrid_command(name='remove', aliases=['rm'])
    async def remove(self, ctx: commands.Context, position: int) -> None:
        """Remove a track from the queue by its position number."""
        gid = ctx.guild.id
        queue = self._state(ctx).queue
        if position < 1 or position > len(queue):
            await ctx.send(embed=MessageWriter.error(t('music.remove.error_range', gid, max=len(queue))))
            return
        items = list(queue)
        removed = items.pop(position - 1)
        queue.clear()
        queue.extend(items)
        await ctx.send(embed=MessageWriter.success(t('music.remove.removed', gid, title=removed.title)))

    @commands.hybrid_command(name='shuffle')
    async def shuffle(self, ctx: commands.Context) -> None:
        """Shuffle the queue."""
        queue = self._state(ctx).queue
        items = list(queue)
        random.shuffle(items)
        queue.clear()
        queue.extend(items)
        await ctx.send(embed=MessageWriter.success(t('music.shuffle.shuffled', ctx.guild.id, count=len(items))))

    # -----------------------------------------------------------------------
    # Voice
    # -----------------------------------------------------------------------

    @commands.hybrid_command(name='join')
    async def join(self, ctx: commands.Context) -> None:
        """Join your voice channel."""
        streamer, _ = await self._ensure_voice(ctx)
        if streamer is not None:
            await ctx.send(embed=MessageWriter.success(t('music.joined', ctx.guild.id)))

    @commands.hybrid_command(name='leave', aliases=['disconnect', 'dc'])
    async def leave(self, ctx: commands.Context) -> None:
        """Leave the voice channel and clear all state."""
        await self._streamer(ctx).leave()
        await ctx.send(embed=MessageWriter.success(t('music.left', ctx.guild.id)))

    # -----------------------------------------------------------------------
    # Playlists
    # -----------------------------------------------------------------------

    @commands.hybrid_group(name='playlist', aliases=['pl'], invoke_without_command=True)
    async def playlist(self, ctx: commands.Context) -> None:
        """Playlist management."""
        gid = ctx.guild.id
        await ctx.send(embed=MessageWriter.info(
            'Playlist commands',
            t('music.playlist_hint', gid),
        ))

    @playlist.command(name='save')
    async def playlist_save(self, ctx: commands.Context, *, name: str) -> None:
        """Save the current queue as a named playlist."""
        gid = ctx.guild.id
        state = self._state(ctx)
        tracks = list(state.queue)
        if state.current_track:
            tracks = [state.current_track] + tracks
        if not tracks:
            await ctx.send(embed=MessageWriter.error(t('music.playlist.save.empty', gid)))
            return
        PlaylistConfig().set(name, [_track_to_dict(tr) for tr in tracks])
        await ctx.send(embed=MessageWriter.success(
            t('music.playlist.save.title', gid, name=name),
            t('music.playlist.save.desc', gid, count=len(tracks)),
        ))

    @playlist.command(name='load')
    async def playlist_load(self, ctx: commands.Context, *, name: str) -> None:
        """Load a playlist into the queue."""
        gid = ctx.guild.id
        data = PlaylistConfig().get(name)
        if data is None:
            await ctx.send(embed=MessageWriter.error(t('music.playlist.load.not_found', gid, name=name)))
            return
        streamer, _ = await self._ensure_voice(ctx)
        if streamer is None:
            return
        tracks = [_dict_to_track(d) for d in data]
        state = self._state(ctx)
        added = 0
        for track in tracks:
            if len(state.queue) >= MAX_QUEUE:
                break
            track.requester = ctx.author
            await streamer.play(track)
            added += 1
        await ctx.send(embed=MessageWriter.success(
            t('music.playlist.load.title', gid, name=name),
            t('music.playlist.load.desc', gid, added=added, total=len(tracks)),
        ))

    @playlist.command(name='list')
    async def playlist_list(self, ctx: commands.Context) -> None:
        """List all saved playlists."""
        gid = ctx.guild.id
        playlists = PlaylistConfig().all()
        if not playlists:
            await ctx.send(embed=MessageWriter.info(t('music.playlist.list.empty', gid)))
            return
        lines = [t('music.playlist.list.entry', gid, name=n, count=len(v)) for n, v in playlists.items()]
        await ctx.send(embed=MessageWriter.info(t('music.playlist.list.title', gid), '\n'.join(lines)))

    @playlist.command(name='delete')
    async def playlist_delete(self, ctx: commands.Context, *, name: str) -> None:
        """Delete a playlist."""
        gid = ctx.guild.id
        if PlaylistConfig().delete(name):
            await ctx.send(embed=MessageWriter.success(t('music.playlist.delete.deleted', gid, name=name)))
        else:
            await ctx.send(embed=MessageWriter.error(t('music.playlist.delete.not_found', gid, name=name)))

    @playlist.command(name='show')
    async def playlist_show(self, ctx: commands.Context, *, name: str) -> None:
        """Show the contents of a playlist."""
        gid = ctx.guild.id
        data = PlaylistConfig().get(name)
        if data is None:
            await ctx.send(embed=MessageWriter.error(t('music.playlist.show.not_found', gid, name=name)))
            return
        tracks = [_dict_to_track(d) for d in data]
        lines = [f'**{i}.** {tr.title}' for i, tr in enumerate(tracks, 1)]
        e = MessageWriter.info(t('music.playlist.show.title', gid, name=name), '\n'.join(lines[:20]))
        if len(tracks) > 20:
            e.set_footer(text=t('music.playlist.show.more', gid, count=len(tracks) - 20))
        await ctx.send(embed=e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
