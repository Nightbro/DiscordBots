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
    def track_card(track: Track, guild_id: int = 0) -> discord.Embed:
        from utils.i18n import t
        e = _embed()
        e.title = f'🎵 {track.title}'
        if track.duration is not None:
            mins, secs = divmod(track.duration, 60)
            e.add_field(name=t('message.track_duration', guild_id), value=f'{mins}:{secs:02d}')
        if track.requester is not None:
            e.add_field(name=t('message.track_requested_by', guild_id), value=track.requester.display_name)
        return e

    @staticmethod
    def queue_page(tracks: list[Track], page: int, total_pages: int, guild_id: int = 0) -> discord.Embed:
        from utils.i18n import t
        e = _embed()
        e.title = t('message.queue_title', guild_id, page=page, total=total_pages)
        if not tracks:
            e.description = t('message.queue_empty', guild_id)
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
    def soundboard_panel(sounds: dict[str, dict], guild_id: int = 0) -> discord.Embed:
        """sounds: {name: {'emoji': str, 'file': str}} mapping from SoundboardConfig."""
        from utils.i18n import t
        e = _embed()
        e.title = t('message.soundboard_title', guild_id)
        if sounds:
            lines = [f'{meta["emoji"]} **{name}**' for name, meta in sounds.items()]
            e.description = '\n'.join(lines)
        else:
            e.description = t('message.soundboard_empty', guild_id)
        return e
