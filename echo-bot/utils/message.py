import discord

from utils.config import BOT_NAME, COLOR
from utils.guild_state import Track

_GREEN = 0x57F287
_RED = 0xED4245


def _embed(color: int = COLOR) -> discord.Embed:
    e = discord.Embed(color=color)
    e.set_footer(text=BOT_NAME)
    return e


class MessageWriter:
    @staticmethod
    def success(title: str, description: str = '') -> discord.Embed:
        e = _embed(_GREEN)
        e.title = f'✅ {title}'
        if description:
            e.description = description
        return e

    @staticmethod
    def error(title: str, description: str = '') -> discord.Embed:
        e = _embed(_RED)
        e.title = f'❌ {title}'
        if description:
            e.description = description
        return e

    @staticmethod
    def info(title: str, description: str = '') -> discord.Embed:
        e = _embed()
        e.title = f'ℹ️ {title}'
        if description:
            e.description = description
        return e

    @staticmethod
    def track_card(track: Track) -> discord.Embed:
        e = _embed()
        e.title = f'🎵 {track.title}'
        if track.duration is not None:
            mins, secs = divmod(track.duration, 60)
            e.add_field(name='Duration', value=f'{mins}:{secs:02d}')
        if track.requester is not None:
            e.add_field(name='Requested by', value=track.requester.display_name)
        return e

    @staticmethod
    def queue_page(tracks: list[Track], page: int, total_pages: int) -> discord.Embed:
        e = _embed()
        e.title = f'🎵 Queue — Page {page}/{total_pages}'
        if not tracks:
            e.description = 'The queue is empty.'
            return e
        offset = (page - 1) * 10
        lines = []
        for i, track in enumerate(tracks, offset + 1):
            dur = ''
            if track.duration is not None:
                mins, secs = divmod(track.duration, 60)
                dur = f' `{mins}:{secs:02d}`'
            lines.append(f'**{i}.** {track.title}{dur}')
        e.description = '\n'.join(lines)
        return e

    @staticmethod
    def soundboard_panel(sounds: dict[str, dict]) -> discord.Embed:
        """sounds: {name: {'emoji': str, 'file': str}} mapping from SoundboardConfig."""
        e = _embed()
        e.title = '🔊 Soundboard'
        if sounds:
            lines = [f'{meta["emoji"]} **{name}**' for name, meta in sounds.items()]
            e.description = '\n'.join(lines)
        else:
            e.description = 'No sounds added yet. Use `!sb add <name>` with an attachment.'
        return e
