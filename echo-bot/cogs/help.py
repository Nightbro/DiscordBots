from __future__ import annotations

import discord
from discord.ext import commands

from utils.config import BOT_NAME, COLOR, PREFIX
from utils.i18n import t

# Ordered page keys: overview first, then one per section
_PAGE_KEYS = ['__overview__', 'music', 'queue', 'intros', 'soundboard', 'tts', 'settings']


def _build_embed(key: str, page_num: int, total: int, guild_id: int) -> discord.Embed:
    if key == '__overview__':
        title = t('help.overview.title', guild_id, bot=BOT_NAME)
        desc = t('help.overview.body', guild_id, prefix=PREFIX, bot=BOT_NAME)
    else:
        title = t(f'help.{key}.title', guild_id, bot=BOT_NAME, prefix=PREFIX)
        desc = t(f'help.{key}.body', guild_id, prefix=PREFIX, bot=BOT_NAME)
    footer = t('help.footer', guild_id, bot=BOT_NAME, page=page_num, total=total)
    e = discord.Embed(title=title, description=desc, color=COLOR)
    e.set_footer(text=footer)
    return e


class _HelpView(discord.ui.View):
    def __init__(self, start_index: int = 0, *, guild_id: int = 0, timeout: float = 120.0) -> None:
        super().__init__(timeout=timeout)
        self._index = start_index
        self._guild_id = guild_id
        self._total = len(_PAGE_KEYS)
        self.prev_button.label = t('help.prev', guild_id)
        self.next_button.label = t('help.next', guild_id)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self._index == 0
        self.next_button.disabled = self._index >= self._total - 1

    def build_embed(self) -> discord.Embed:
        return _build_embed(_PAGE_KEYS[self._index], self._index + 1, self._total, self._guild_id)

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


class HelpCog(commands.Cog, name='Help'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name='help', aliases=['h'])
    async def help_cmd(self, ctx: commands.Context, section: str = '') -> None:
        """Show help. Optionally pass a section: music, queue, intros, soundboard, tts, settings."""
        guild_id = ctx.guild.id if ctx.guild else 0
        section = section.lower().strip()

        sections = [k for k in _PAGE_KEYS if k != '__overview__']
        if section and section in sections:
            index = _PAGE_KEYS.index(section)
        else:
            index = 0

        view = _HelpView(start_index=index, guild_id=guild_id)
        await ctx.send(embed=view.build_embed(), view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
