from __future__ import annotations

import random
from typing import Any

import discord
from discord.ext import commands

from utils.config import EMOJI_LOADING, EMOJI_MUSIC, MAX_QUEUE
from utils.downloader import Downloader
from utils.guild_state import GuildState, Track
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
        """
        Ensure the bot is in the user's voice channel.

        Returns (streamer, just_connected). Returns (None, False) and sends an
        error embed when the user is not in a voice channel.
        """
        if ctx.author.voice is None:
            await ctx.send(embed=MessageWriter.error('You must be in a voice channel.'))
            return None, False

        streamer = self._streamer(ctx)
        state = self._state(ctx)
        just_connected = state.voice_client is None

        await streamer.join(ctx.author.voice.channel)
        return streamer, just_connected

    # -----------------------------------------------------------------------
    # Playback
    # -----------------------------------------------------------------------

    @commands.hybrid_command(name='play', aliases=['p'])
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        """Add a track to the queue and start playback."""
        streamer, _ = await self._ensure_voice(ctx)
        if streamer is None:
            return

        loading = await ctx.send(embed=MessageWriter.info(f'{EMOJI_LOADING} Resolving…'))

        try:
            track = await Downloader.resolve(query)
            track.requester = ctx.author
        except Exception as exc:
            await loading.edit(embed=MessageWriter.error('Could not resolve track.', str(exc)))
            return

        try:
            await streamer.play(track)
        except ValueError as exc:
            await loading.edit(embed=MessageWriter.error(str(exc)))
            return

        await loading.edit(embed=MessageWriter.track_card(track))

    @commands.hybrid_command(name='skip', aliases=['s'])
    async def skip(self, ctx: commands.Context) -> None:
        """Skip the current track."""
        streamer = self._streamer(ctx)
        skipped = await streamer.skip()
        if skipped:
            await ctx.send(embed=MessageWriter.success(f'Skipped **{skipped.title}**'))
        else:
            await ctx.send(embed=MessageWriter.error('Nothing is playing.'))

    @commands.hybrid_command(name='pause')
    async def pause(self, ctx: commands.Context) -> None:
        """Pause playback."""
        await self._streamer(ctx).pause()
        await ctx.send(embed=MessageWriter.success('Paused.'))

    @commands.hybrid_command(name='resume', aliases=['unpause'])
    async def resume(self, ctx: commands.Context) -> None:
        """Resume playback."""
        await self._streamer(ctx).resume()
        await ctx.send(embed=MessageWriter.success('Resumed.'))

    @commands.hybrid_command(name='stop')
    async def stop(self, ctx: commands.Context) -> None:
        """Stop playback and clear the queue."""
        await self._streamer(ctx).stop()
        await ctx.send(embed=MessageWriter.success('Stopped and queue cleared.'))

    @commands.hybrid_command(name='nowplaying', aliases=['np'])
    async def now_playing(self, ctx: commands.Context) -> None:
        """Show the currently playing track."""
        track = self._state(ctx).current_track
        if track:
            await ctx.send(embed=MessageWriter.track_card(track))
        else:
            await ctx.send(embed=MessageWriter.info('Nothing is playing right now.'))

    # -----------------------------------------------------------------------
    # Queue
    # -----------------------------------------------------------------------

    @commands.hybrid_command(name='queue', aliases=['q'])
    async def queue(self, ctx: commands.Context, page: int = 1) -> None:
        """Show the playback queue."""
        state = self._state(ctx)
        tracks = list(state.queue)
        total = len(tracks)
        total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
        page = max(1, min(page, total_pages))
        chunk = tracks[(page - 1) * _PAGE_SIZE: page * _PAGE_SIZE]

        embed = MessageWriter.queue_page(chunk, page, total_pages)

        if state.current_track:
            t = state.current_track
            dur = ''
            if t.duration is not None:
                m, s = divmod(t.duration, 60)
                dur = f' `{m}:{s:02d}`'
            now_playing_line = f'{EMOJI_MUSIC} **Now playing:** {t.title}{dur}\n\n'
            embed.description = now_playing_line + (embed.description or '')

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='clear')
    async def clear(self, ctx: commands.Context) -> None:
        """Clear the queue (keeps current track playing)."""
        self._state(ctx).queue.clear()
        await ctx.send(embed=MessageWriter.success('Queue cleared.'))

    @commands.hybrid_command(name='remove', aliases=['rm'])
    async def remove(self, ctx: commands.Context, position: int) -> None:
        """Remove a track from the queue by its position number."""
        queue = self._state(ctx).queue
        if position < 1 or position > len(queue):
            await ctx.send(embed=MessageWriter.error(f'Position must be between 1 and {len(queue)}.'))
            return
        items = list(queue)
        removed = items.pop(position - 1)
        queue.clear()
        queue.extend(items)
        await ctx.send(embed=MessageWriter.success(f'Removed **{removed.title}**'))

    @commands.hybrid_command(name='shuffle')
    async def shuffle(self, ctx: commands.Context) -> None:
        """Shuffle the queue."""
        queue = self._state(ctx).queue
        items = list(queue)
        random.shuffle(items)
        queue.clear()
        queue.extend(items)
        await ctx.send(embed=MessageWriter.success(f'Shuffled {len(items)} tracks.'))

    # -----------------------------------------------------------------------
    # Voice
    # -----------------------------------------------------------------------

    @commands.hybrid_command(name='join')
    async def join(self, ctx: commands.Context) -> None:
        """Join your voice channel."""
        streamer, _ = await self._ensure_voice(ctx)
        if streamer is not None:
            await ctx.send(embed=MessageWriter.success('Joined your channel.'))

    @commands.hybrid_command(name='leave', aliases=['disconnect', 'dc'])
    async def leave(self, ctx: commands.Context) -> None:
        """Leave the voice channel and clear all state."""
        await self._streamer(ctx).leave()
        await ctx.send(embed=MessageWriter.success('Left the voice channel.'))

    # -----------------------------------------------------------------------
    # Playlists
    # -----------------------------------------------------------------------

    @commands.hybrid_group(name='playlist', aliases=['pl'], invoke_without_command=True)
    async def playlist(self, ctx: commands.Context) -> None:
        """Playlist management."""
        await ctx.send(embed=MessageWriter.info(
            'Playlist commands',
            '`save <name>` · `load <name>` · `list` · `delete <name>` · `show <name>`',
        ))

    @playlist.command(name='save')
    async def playlist_save(self, ctx: commands.Context, *, name: str) -> None:
        """Save the current queue as a named playlist."""
        state = self._state(ctx)
        tracks = list(state.queue)
        if state.current_track:
            tracks = [state.current_track] + tracks
        if not tracks:
            await ctx.send(embed=MessageWriter.error('Nothing in the queue to save.'))
            return

        cfg = PlaylistConfig()
        cfg.set(name, [_track_to_dict(t) for t in tracks])
        await ctx.send(embed=MessageWriter.success(
            f'Saved playlist **{name}**',
            f'{len(tracks)} tracks.',
        ))

    @playlist.command(name='load')
    async def playlist_load(self, ctx: commands.Context, *, name: str) -> None:
        """Load a playlist into the queue."""
        cfg = PlaylistConfig()
        data = cfg.get(name)
        if data is None:
            await ctx.send(embed=MessageWriter.error(f'Playlist **{name}** not found.'))
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
            f'Loaded **{name}**',
            f'Added {added}/{len(tracks)} tracks to the queue.',
        ))

    @playlist.command(name='list')
    async def playlist_list(self, ctx: commands.Context) -> None:
        """List all saved playlists."""
        playlists = PlaylistConfig().all()
        if not playlists:
            await ctx.send(embed=MessageWriter.info('No playlists saved yet.'))
            return
        lines = [f'• **{name}** ({len(tracks)} tracks)' for name, tracks in playlists.items()]
        await ctx.send(embed=MessageWriter.info('Saved playlists', '\n'.join(lines)))

    @playlist.command(name='delete')
    async def playlist_delete(self, ctx: commands.Context, *, name: str) -> None:
        """Delete a playlist."""
        cfg = PlaylistConfig()
        if cfg.delete(name):
            await ctx.send(embed=MessageWriter.success(f'Deleted playlist **{name}**.'))
        else:
            await ctx.send(embed=MessageWriter.error(f'Playlist **{name}** not found.'))

    @playlist.command(name='show')
    async def playlist_show(self, ctx: commands.Context, *, name: str) -> None:
        """Show the contents of a playlist."""
        cfg = PlaylistConfig()
        data = cfg.get(name)
        if data is None:
            await ctx.send(embed=MessageWriter.error(f'Playlist **{name}** not found.'))
            return
        tracks = [_dict_to_track(d) for d in data]
        lines = [f'**{i}.** {t.title}' for i, t in enumerate(tracks, 1)]
        e = MessageWriter.info(f'Playlist: {name}', '\n'.join(lines[:20]))
        if len(tracks) > 20:
            e.set_footer(text=f'… and {len(tracks) - 20} more')
        await ctx.send(embed=e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
