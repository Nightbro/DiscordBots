import asyncio
import json
import logging
from pathlib import Path

import discord
from discord.ext import commands

from utils.config import PLAYLISTS_FILE, DOWNLOADS_DIR, _INTRO_ON_BOT_JOIN
from utils.downloader import download_track, is_suno_url, duration_tag, FFMPEG_OPTIONS
from utils.player import get_state, play_next
from utils.intro_config import get_intro_file

log = logging.getLogger('music-bot.music')

_HELP_PAGES = [
    """\
**Music Bot — Commands** · Page 1/2

**Playback**
`!join` (`!j`) — Join your voice channel without playing anything.
`!play <url/search>` (`!p`) — Play from YouTube, Suno, or a search query. Queues if already playing.
`!skip` (`!s`) — Skip the current song.
`!pause` — Pause playback.
`!resume` (`!r`) — Resume paused playback.
`!stop` — Stop, clear the queue, and disconnect.
`!queue` (`!q`) — Show the current playback queue.
`!clear` — Clear the queue without stopping the current song.
`!leave` (`!dc`) — Disconnect from the voice channel.
`!cleanup` — Delete all cached audio files.

**Playlists** (`!playlist` / `!pl`)
`!pl save <name>` — Save the current queue as a playlist.
`!pl load <name>` — Load a playlist into the queue.
`!pl list` — List all saved playlists.
`!pl show <name>` — Show tracks in a playlist.
`!pl add <name> <url>` — Add a track to an existing playlist.
`!pl remove <name> <number>` — Remove a track by its number.
`!pl delete <name>` — Delete a playlist entirely.\
""",
    """\
**Music Bot — Commands** · Page 2/2

**Intro Sounds** (`!intro` / `!in`)
`!intro set bot <url>` — Set the bot-join intro (attach MP3 or provide URL/search).
`!intro set user <url>` — Set the server-wide user-join intro (attach MP3 or provide URL/search).
`!intro set @user <url>` — Set a per-user intro for a specific member.
`!intro clear bot` — Remove the bot-join intro.
`!intro clear user` — Remove the server-wide user-join intro.
`!intro clear @user` — Remove a specific user's intro.
`!intro list` — List all configured intro triggers for this server.
`!intro show` — Show bot/server-wide config and global enable flags.
`!intro rename bot|user|@user <name>` — Give an intro a human-readable label shown in `!intro list`.
`!intro trigger bot|user|@user` — Manually play an intro (bot must be idle in voice).
`!intro autojoin on|off` — Auto-join the voice channel when the first user enters.

**Soundboard** (`!soundboard` / `!sb`)
`!sb add <name> <emoji> [url/search]` — Add a sound (attach MP3 or provide URL/search).
`!sb remove <name>` — Remove a sound.
`!sb trigger <name>` — Play a sound (bot must be idle in voice).
`!sb list` — List all sounds configured for this server.\
""",
]


class _HelpView(discord.ui.View):
    def __init__(self, pages: list[str]):
        super().__init__(timeout=120)
        self.pages = pages
        self.index = 0
        self.message: discord.Message | None = None
        self._refresh()

    def _refresh(self):
        self.prev_btn.disabled = self.index == 0
        self.next_btn.disabled = self.index == len(self.pages) - 1

    @discord.ui.button(label='◀  Prev', style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index -= 1
        self._refresh()
        await interaction.response.edit_message(content=self.pages[self.index], view=self)

    @discord.ui.button(label='Next  ▶', style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index += 1
        self._refresh()
        await interaction.response.edit_message(content=self.pages[self.index], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class MusicCog(commands.Cog, name='Music'):
    def __init__(self, bot):
        self.bot = bot

    # ── Voice helpers ─────────────────────────────────────────────────────────

    async def _ensure_voice(self, ctx: commands.Context) -> bool:
        if not ctx.author.voice:
            await ctx.send('You need to be in a voice channel.')
            return False
        channel = ctx.author.voice.channel
        state = get_state(self.bot, ctx.guild.id)
        vc = state['voice_client']
        if vc is None or not vc.is_connected():
            state['voice_client'] = await channel.connect()
            state['just_connected'] = True
        else:
            state['just_connected'] = False
            if vc.channel != channel:
                await vc.move_to(channel)
        return True

    # ── Playlist helpers ──────────────────────────────────────────────────────

    def _load_playlists(self) -> dict:
        if PLAYLISTS_FILE.exists():
            return json.loads(PLAYLISTS_FILE.read_text(encoding='utf-8'))
        return {}

    def _save_playlists(self, data: dict):
        PLAYLISTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

    def _track_to_storable(self, track: dict) -> dict:
        return {k: v for k, v in track.items() if k not in ('file', 'from_cache')}

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(name='help', aliases=['h'])
    async def help_cmd(self, ctx: commands.Context):
        view = _HelpView(_HELP_PAGES)
        view.message = await ctx.send(_HELP_PAGES[0], view=view)

    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx: commands.Context, *, query: str):
        """Play a YouTube URL/search or Suno URL. Queues if already playing."""
        if not await self._ensure_voice(ctx):
            return

        log.info('Play request from %s in guild %s: %r', ctx.author, ctx.guild.id, query)
        label = 'Suno track' if is_suno_url(query) else f'`{query}`'
        await ctx.send(f'Loading {label}...')

        try:
            loop = asyncio.get_event_loop()
            track = await loop.run_in_executor(None, download_track, query)
        except Exception as e:
            log.error('Download failed for %r: %s', query, e, exc_info=True)
            return await ctx.send(f'Could not download: `{e}`')

        state = get_state(self.bot, ctx.guild.id)
        just_connected = state.pop('just_connected', False)
        state['queue'].append(track)
        if just_connected and _INTRO_ON_BOT_JOIN:
            intro = get_intro_file(ctx.guild.id, 'bot')
            if intro:
                state['queue'].appendleft({'file': str(intro), 'title': None, 'duration': 0, '_intro': True})
        if state['voice_client'].is_playing() or state['voice_client'].is_paused():
            cache_note = ' *(cached)*' if track.get('from_cache') else ''
            await ctx.send(
                f'Added to queue: **{track["title"]}**{duration_tag(track["duration"])}'
                f'{cache_note} (#{len(state["queue"])})'
            )
        else:
            await play_next(self.bot, ctx.guild.id, ctx.channel)

    @commands.command(name='skip', aliases=['s'])
    async def skip(self, ctx: commands.Context):
        state = get_state(self.bot, ctx.guild.id)
        vc = state['voice_client']
        if vc and vc.is_playing():
            vc.stop()
            await ctx.send('Skipped.')
        else:
            await ctx.send('Nothing is playing.')

    @commands.command(name='pause')
    async def pause(self, ctx: commands.Context):
        state = get_state(self.bot, ctx.guild.id)
        vc = state['voice_client']
        if vc and vc.is_playing():
            vc.pause()
            await ctx.send('Paused.')
        else:
            await ctx.send('Nothing is playing.')

    @commands.command(name='resume', aliases=['r'])
    async def resume(self, ctx: commands.Context):
        state = get_state(self.bot, ctx.guild.id)
        vc = state['voice_client']
        if vc and vc.is_paused():
            vc.resume()
            await ctx.send('Resumed.')
        else:
            await ctx.send('Nothing is paused.')

    @commands.command(name='stop')
    async def stop(self, ctx: commands.Context):
        state = get_state(self.bot, ctx.guild.id)
        state['queue'].clear()
        vc = state['voice_client']
        if vc:
            vc.stop()
            await vc.disconnect()
            state['voice_client'] = None
        await ctx.send('Stopped and disconnected.')

    @commands.command(name='queue', aliases=['q'])
    async def show_queue(self, ctx: commands.Context):
        state = get_state(self.bot, ctx.guild.id)
        visible = [t for t in state['queue'] if not t.get('_intro')]
        if not visible:
            return await ctx.send('The queue is empty.')
        lines = [
            f'`{i}.` **{t["title"]}**{duration_tag(t["duration"])}'
            for i, t in enumerate(visible, 1)
        ]
        await ctx.send('**Queue:**\n' + '\n'.join(lines))

    @commands.command(name='clear')
    async def clear(self, ctx: commands.Context):
        get_state(self.bot, ctx.guild.id)['queue'].clear()
        await ctx.send('Queue cleared.')

    @commands.command(name='join', aliases=['j'])
    async def join(self, ctx: commands.Context):
        if not await self._ensure_voice(ctx):
            return
        state = get_state(self.bot, ctx.guild.id)
        if state.pop('just_connected', False) and _INTRO_ON_BOT_JOIN:
            intro = get_intro_file(ctx.guild.id, 'bot')
            if intro:
                state['voice_client'].play(discord.FFmpegPCMAudio(str(intro), **FFMPEG_OPTIONS))
        await ctx.send(f'Joined **{ctx.author.voice.channel.name}**.')

    @commands.command(name='leave', aliases=['dc'])
    async def leave(self, ctx: commands.Context):
        state = get_state(self.bot, ctx.guild.id)
        vc = state['voice_client']
        if vc and vc.is_connected():
            state['queue'].clear()
            await vc.disconnect()
            state['voice_client'] = None
            await ctx.send('Disconnected.')
        else:
            await ctx.send('Not connected to a voice channel.')

    @commands.command(name='cleanup')
    async def cleanup(self, ctx: commands.Context):
        files = list(DOWNLOADS_DIR.glob('*.mp3'))
        for f in files:
            f.unlink(missing_ok=True)
        log.info('Cleanup: deleted %d cached file(s) (requested by %s)', len(files), ctx.author)
        await ctx.send(f'Deleted {len(files)} cached file(s).')

    # ── Playlists ─────────────────────────────────────────────────────────────

    @commands.group(name='playlist', aliases=['pl'], invoke_without_command=True)
    async def playlist_group(self, ctx: commands.Context):
        await ctx.send(
            '**Playlist commands:**\n'
            '`!pl save <name>` — save current queue as a playlist\n'
            '`!pl load <name>` — load playlist into queue\n'
            '`!pl list` — list all saved playlists\n'
            '`!pl show <name>` — show tracks in a playlist\n'
            '`!pl add <name> <url>` — add a track to an existing playlist\n'
            '`!pl remove <name> <number>` — remove a track by its number\n'
            '`!pl delete <name>` — delete a playlist entirely'
        )

    @playlist_group.command(name='save')
    async def playlist_save(self, ctx: commands.Context, *, name: str):
        state = get_state(self.bot, ctx.guild.id)
        if not state['queue']:
            return await ctx.send('The queue is empty — nothing to save.')
        data = self._load_playlists()
        data.setdefault(str(ctx.guild.id), {})[name] = [
            self._track_to_storable(t) for t in state['queue'] if not t.get('_intro')
        ]
        self._save_playlists(data)
        log.info('Playlist saved: "%s" (%d tracks) by %s', name, len(state['queue']), ctx.author)
        await ctx.send(f'Saved **{name}** with {len(state["queue"])} track(s).')

    @playlist_group.command(name='load')
    async def playlist_load(self, ctx: commands.Context, *, name: str):
        if not await self._ensure_voice(ctx):
            return
        data   = self._load_playlists()
        tracks = data.get(str(ctx.guild.id), {}).get(name)
        if not tracks:
            return await ctx.send(f'No playlist named **{name}**. Use `!pl list` to see all.')
        state = get_state(self.bot, ctx.guild.id)
        state['queue'].extend(tracks)
        log.info('Playlist loaded: "%s" (%d tracks) by %s', name, len(tracks), ctx.author)
        await ctx.send(f'Loaded **{name}** — {len(tracks)} track(s) added to queue.')
        if not (state['voice_client'].is_playing() or state['voice_client'].is_paused()):
            await play_next(self.bot, ctx.guild.id, ctx.channel)

    @playlist_group.command(name='list')
    async def playlist_list(self, ctx: commands.Context):
        data      = self._load_playlists()
        playlists = data.get(str(ctx.guild.id), {})
        if not playlists:
            return await ctx.send('No saved playlists yet.')
        lines = [f'`{name}` — {len(tracks)} track(s)' for name, tracks in playlists.items()]
        await ctx.send('**Saved playlists:**\n' + '\n'.join(lines))

    @playlist_group.command(name='show')
    async def playlist_show(self, ctx: commands.Context, *, name: str):
        data   = self._load_playlists()
        tracks = data.get(str(ctx.guild.id), {}).get(name)
        if tracks is None:
            return await ctx.send(f'No playlist named **{name}**.')
        if not tracks:
            return await ctx.send(f'**{name}** is empty.')
        lines = [
            f'`{i}.` **{t["title"]}**{duration_tag(t["duration"])}'
            for i, t in enumerate(tracks, 1)
        ]
        await ctx.send(f'**{name}** ({len(tracks)} tracks):\n' + '\n'.join(lines))

    @playlist_group.command(name='add')
    async def playlist_add(self, ctx: commands.Context, name: str, *, url: str):
        data = self._load_playlists()
        gid  = str(ctx.guild.id)
        if name not in data.get(gid, {}):
            return await ctx.send(
                f'No playlist named **{name}**. '
                f'Create one first with `!pl save {name}` after queuing some tracks.'
            )
        await ctx.send('Downloading track info...')
        try:
            loop  = asyncio.get_event_loop()
            track = await loop.run_in_executor(None, download_track, url)
        except Exception as e:
            log.error('Failed to add track to playlist "%s": %s', name, e, exc_info=True)
            return await ctx.send(f'Could not fetch track: `{e}`')
        data[gid][name].append(self._track_to_storable(track))
        self._save_playlists(data)
        log.info('Track added to playlist "%s": %s (by %s)', name, track['title'], ctx.author)
        await ctx.send(f'Added **{track["title"]}** to **{name}**.')

    @playlist_group.command(name='remove')
    async def playlist_remove(self, ctx: commands.Context, name: str, number: int):
        data   = self._load_playlists()
        gid    = str(ctx.guild.id)
        tracks = data.get(gid, {}).get(name)
        if tracks is None:
            return await ctx.send(f'No playlist named **{name}**.')
        if number < 1 or number > len(tracks):
            return await ctx.send(f'Number must be between 1 and {len(tracks)}.')
        removed = tracks.pop(number - 1)
        self._save_playlists(data)
        await ctx.send(f'Removed **{removed["title"]}** from **{name}**.')

    @playlist_group.command(name='delete')
    async def playlist_delete(self, ctx: commands.Context, *, name: str):
        data = self._load_playlists()
        gid  = str(ctx.guild.id)
        if name not in data.get(gid, {}):
            return await ctx.send(f'No playlist named **{name}**.')
        del data[gid][name]
        self._save_playlists(data)
        log.info('Playlist deleted: "%s" by %s', name, ctx.author)
        await ctx.send(f'Deleted playlist **{name}**.')


async def setup(bot):
    await bot.add_cog(MusicCog(bot))
