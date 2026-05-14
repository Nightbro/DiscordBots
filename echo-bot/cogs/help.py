from __future__ import annotations

import discord
from discord.ext import commands

from utils.config import BOT_NAME, COLOR, PREFIX

# ---------------------------------------------------------------------------
# Help pages — one per section
# ---------------------------------------------------------------------------

_SECTIONS: dict[str, tuple[str, str]] = {
    'music': (
        '🎵 Music — Playback',
        f'`{PREFIX}play <url|search>` — add a track to the queue\n'
        f'`{PREFIX}skip` — skip the current track\n'
        f'`{PREFIX}pause` — pause playback\n'
        f'`{PREFIX}resume` — resume playback\n'
        f'`{PREFIX}stop` — stop and clear the queue\n'
        f'`{PREFIX}nowplaying` (`{PREFIX}np`) — show current track\n'
        f'`{PREFIX}join` — join your voice channel\n'
        f'`{PREFIX}leave` — leave the voice channel\n',
    ),
    'queue': (
        '📋 Music — Queue & Playlists',
        f'`{PREFIX}queue [page]` (`{PREFIX}q`) — show the queue\n'
        f'`{PREFIX}clear` — clear the queue (keeps current track)\n'
        f'`{PREFIX}remove <#>` — remove a track by position\n'
        f'`{PREFIX}shuffle` — shuffle the queue\n'
        '\n'
        f'`{PREFIX}playlist save <name>` — save queue as playlist\n'
        f'`{PREFIX}playlist load <name>` — load a playlist\n'
        f'`{PREFIX}playlist list` — list saved playlists\n'
        f'`{PREFIX}playlist delete <name>` — delete a playlist\n'
        f'`{PREFIX}playlist show <name>` — show playlist contents\n',
    ),
    'intros': (
        '👋 Intros',
        f'`{PREFIX}intro set` — set your default intro (attach audio)\n'
        f'`{PREFIX}intro schedule <days>` — set intro for specific days (e.g. `mon,fri`)\n'
        f'`{PREFIX}intro override <YYYY-MM-DD>` — set a one-off date intro\n'
        f'`{PREFIX}intro unschedule <days>` — remove scheduled days\n'
        f'`{PREFIX}intro clear` — remove all your intro settings\n'
        f'`{PREFIX}intro show` — show your current intro config\n'
        f'`{PREFIX}intro list` — list all intro configs on this server\n'
        f'`{PREFIX}intro trigger` — play your intro now\n'
        f'`{PREFIX}intro autojoin <true|false>` — toggle bot auto-join\n'
        '\n'
        f'Supported audio: `.mp3 .ogg .wav .flac .m4a .opus .aac`\n',
    ),
    'soundboard': (
        '🔊 Soundboard',
        f'`{PREFIX}sb add <name> [emoji]` — add a sound (attach audio)\n'
        f'`{PREFIX}sb remove <name>` — remove a sound and its file\n'
        f'`{PREFIX}sb play <name>` — play a sound in your channel\n'
        f'`{PREFIX}sb list` — list all sounds\n'
        f'`{PREFIX}sb panel` — post a reaction panel (react to play)\n'
        '\n'
        f'Aliases: `{PREFIX}soundboard`\n',
    ),
    'tts': (
        '🗣️ TTS',
        'Text-to-speech commands are coming in a future update.\n',
    ),
    'settings': (
        '⚙️ Settings (admins only)',
        f'`{PREFIX}settings` — show current per-server settings\n'
        f'`{PREFIX}settings set <key> <true|false>` — override a setting for this server\n'
        f'`{PREFIX}settings reset <key>` — revert to the global default\n'
        '\n'
        '**Available keys:**\n'
        '`auto_join` — join when the first person enters a channel\n'
        '`auto_leave` — leave when the last person exits the channel\n',
    ),
}

_OVERVIEW = (
    f'**{BOT_NAME} Help**',
    f'Use `{PREFIX}help <section>` or the buttons below to browse.\n'
    '\n'
    '`music` — playback controls\n'
    '`queue` — queue & playlists\n'
    '`intros` — per-user join sounds\n'
    '`soundboard` — reaction soundboard\n'
    '`tts` — text-to-speech *(coming soon)*\n'
    '`settings` — per-server settings *(admins)*\n'
    '\n'
    f'All commands also work as slash commands — type `/` to browse.\n',
)

# Ordered list for Prev/Next navigation: overview first, then sections
_PAGE_KEYS = ['__overview__'] + list(_SECTIONS)


def _build_embed(key: str, page_num: int, total: int) -> discord.Embed:
    if key == '__overview__':
        title, desc = _OVERVIEW
    else:
        title, desc = _SECTIONS[key]
    e = discord.Embed(title=title, description=desc, color=COLOR)
    e.set_footer(text=f'{BOT_NAME} • Page {page_num}/{total}')
    return e


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

class _HelpView(discord.ui.View):
    def __init__(self, start_index: int = 0, *, timeout: float = 120.0) -> None:
        super().__init__(timeout=timeout)
        self._index = start_index
        self._total = len(_PAGE_KEYS)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self._index == 0
        self.next_button.disabled = self._index >= self._total - 1

    def build_embed(self) -> discord.Embed:
        return _build_embed(_PAGE_KEYS[self._index], self._index + 1, self._total)

    @discord.ui.button(label='◀ Prev', style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self._index -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='Next ▶', style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self._index += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class HelpCog(commands.Cog, name='Help'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name='help', aliases=['h'])
    async def help_cmd(self, ctx: commands.Context, section: str = '') -> None:
        """Show help. Optionally pass a section: music, queue, intros, soundboard, tts."""
        section = section.lower().strip()

        if section and section in _SECTIONS:
            index = _PAGE_KEYS.index(section)
        else:
            index = 0  # overview

        view = _HelpView(start_index=index)
        await ctx.send(embed=view.build_embed(), view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
