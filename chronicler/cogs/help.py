from __future__ import annotations

import discord
from discord.ext import commands

from utils.config import BOT_NAME, PREFIX
from utils.guild_config import get_all_settings
from utils.message import MessageWriter

# One entry per help page. The first is the landing page; the rest are
# reachable by name with "!help <key>", and the overview lists each key in
# backticks so the names are discoverable (a test enforces that).
#
# Bodies must name every visible command with its prefix — the help-coverage
# test in tests/test_help_cog.py fails the build otherwise. They must also not
# name anything that is *not* a command: "!join" would be flagged as a ghost,
# which is why the DM keyword below is written without a prefix.
_PAGES: dict[str, dict[str, str]] = {
    '__overview__': {
        'title': '{bot} — Commands',
        'body': """
{bot} keeps the table: dice now, with announcements, characters and session
notes to come.

**Pages**
`rolling` — rolling dice, advantage, success pools
`archive` — exporting a channel to a readable bundle
`settings` — per-server configuration

Use `{p}help rolling` or `{p}help settings`, or the buttons below.

**Everything else**
`{p}help` — this message
`{p}version` — running version
`{p}ping` — latency check

Alias: `{p}r` for `{p}roll`. Every command also works as a `/` slash command.
DM me the word `join` and I will send the invite link.
""",
    },
    'rolling': {
        'title': '{bot} — Rolling',
        'body': """
`{p}roll` — roll `1d{die}`
`{p}roll 5` — roll `5d{die}` (this server's default die)
`{p}roll 2d6+3` — any number of dice, plus or minus a modifier
`{p}roll d20+2d4+1` — combine groups
`{p}roll adv +5` — advantage (rolls two d20, keeps the highest)
`{p}roll dis +5` — disadvantage (keeps the lowest)
`{p}roll 2d6+3 sneak attack` — anything after the dice is shown as a label

**Counting successes**
`{p}roll 5 (6)` — roll 5 dice, count how many are 6 or higher
`{p}roll 6d10 (7)` — same, with explicit dice

{system_note}
""",
    },
    'archive': {
        'title': '{bot} — Channel archive',
        'body': """
Exports a channel's messages, images and files into one zip you can open in a
browser. Needs **Manage Server**.

`{p}archive run last 500` — export the most recent 500 messages
`{p}archive run from <message_id>` — export from that message onwards
`{p}archive run from <id> to <id>` — export between two messages
`{p}archive run #other last 200` — export a different channel
`{p}archive status` — what has been exported from this server
`{p}archive` — the same summary

**A range is always required.** There is no default, on purpose.

The bundle holds `index.html` to read it, `transcript.pdf` and
`transcript.docx` of the same messages, the images and files exactly as they
were uploaded, and a `manifest.json` listing every message id. Images are saved
locally rather than linked, because Discord's own links expire after a day.

It is always saved on the host machine, and also attached here when it is small
enough for this server's upload limit.

**Clearing a channel:** add `--purge` to delete the messages the export just
saved. It asks first and a timeout deletes nothing. Only the ids written into
that bundle are removed, and only if the bundle is still readable. Needs
**Manage Messages**.

`{p}archive seed <count>` — owner only, posts numbered test messages so an
export can be tried against a throwaway channel.
""",
    },
    'settings': {
        'title': '{bot} — Server settings',
        'body': """
These need the **Manage Server** permission.

`{p}config` — show this server's roll settings
`{p}config show` — the same card
`{p}config system <standard|wod>` — how rolls are scored
`{p}config die <sides>` — the default die for pool rolls
`{p}config difficulty <n>` — the default success target
`{p}config ones <on|off>` — whether each 1 cancels a success
`{p}config reset` — drop every override

Alias: `{p}settings` works the same as `{p}config`.
""",
    },
}

_PAGE_KEYS = list(_PAGES)

_WOD_NOTE = (
    'This server uses **World of Darkness** rules: a plain pool roll is scored '
    'at difficulty `{diff}` automatically, and each `1` cancels a success.'
)

_STANDARD_NOTE = (
    'This server sums dice by default — add `(n)` to any roll to count hits '
    'instead. The server settings page explains how to switch to World of '
    'Darkness scoring.'
)


def _render(key: str, guild_id: int) -> tuple[str, str]:
    """Title and body for one page, filled in for this server's settings."""
    settings = get_all_settings(guild_id)
    note = _WOD_NOTE if settings['system'] == 'wod' else _STANDARD_NOTE
    page = _PAGES[key]
    fields = {
        'bot': BOT_NAME,
        'p': PREFIX,
        'die': settings['die'],
        'system_note': note.format(diff=settings['difficulty']),
    }
    return page['title'].format(**fields), page['body'].format(**fields).strip()


def _build_embed(key: str, page_num: int, total: int, guild_id: int) -> discord.Embed:
    title, body = _render(key, guild_id)
    return MessageWriter.help_page(title, body, page_num, total)


class _HelpView(discord.ui.View):
    """Prev/next buttons over the help pages."""

    def __init__(self, guild_id: int, index: int = 0) -> None:
        super().__init__(timeout=120.0)
        self._guild_id = guild_id
        self._index = index
        self._total = len(_PAGE_KEYS)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self._index == 0
        self.next_button.disabled = self._index >= self._total - 1

    def build_embed(self) -> discord.Embed:
        return _build_embed(
            _PAGE_KEYS[self._index], self._index + 1, self._total, self._guild_id
        )

    async def _turn(self, interaction: discord.Interaction, step: int) -> None:
        self._index = max(0, min(self._total - 1, self._index + step))
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='◀', style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await self._turn(interaction, -1)

    @discord.ui.button(label='▶', style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await self._turn(interaction, 1)


class HelpCog(commands.Cog, name='Help'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name='help', aliases=['h'])
    async def help_cmd(self, ctx: commands.Context, section: str = '') -> None:
        """Show the command reference. Optionally: !help rolling"""
        guild_id = ctx.guild.id if ctx.guild else 0
        key = section.strip().lower()
        index = _PAGE_KEYS.index(key) if key in _PAGE_KEYS else 0
        view = _HelpView(guild_id, index)
        await ctx.send(embed=view.build_embed(), view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
