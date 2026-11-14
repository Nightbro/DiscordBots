"""The help cog, and the guards that stop documentation drifting from code.

The coverage tests open help.md and FEATURES.md by relative path, so the suite
must be run from the chronicler/ folder (`python -m pytest`).
"""

import itertools
import re
from pathlib import Path

import pytest

from cogs.dev import DevCog
from cogs.help import _PAGE_KEYS, _HelpView, _render, HelpCog
from conftest import sent_embed
from utils.config import BOT_NAME, PREFIX, VERSION


def _cog(mock_bot) -> HelpCog:
    return HelpCog(mock_bot)


# ---------------------------------------------------------------------------
# !help
# ---------------------------------------------------------------------------

async def test_help_opens_on_the_overview(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.help_cmd.callback(cog, ctx, section='')
    embed = sent_embed(ctx)
    assert BOT_NAME in embed.title
    assert f'{PREFIX}help' in embed.description


async def test_help_sends_a_view_for_paging(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.help_cmd.callback(cog, ctx, section='')
    assert ctx.send.call_args.kwargs.get('view') is not None


@pytest.mark.parametrize('section', [k for k in _PAGE_KEYS if k != '__overview__'])
async def test_help_jumps_to_each_named_section(mock_bot, ctx, section):
    cog = _cog(mock_bot)
    await cog.help_cmd.callback(cog, ctx, section=section)
    ctx.send.assert_awaited_once()


async def test_unknown_section_falls_back_to_the_overview(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.help_cmd.callback(cog, ctx, section='nonsense')
    title, _ = _render('__overview__', ctx.guild.id)
    assert sent_embed(ctx).title == title


async def test_rolling_page_documents_advantage(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.help_cmd.callback(cog, ctx, section='rolling')
    assert 'advantage' in sent_embed(ctx).description


def test_rolling_page_adapts_to_the_server_system(guild_id):
    from utils.guild_config import set_system
    _, standard = _render('rolling', guild_id)
    set_system(guild_id, 'wod')
    _, wod = _render('rolling', guild_id)
    assert 'World of Darkness' in wod
    assert standard != wod


def test_rolling_page_shows_the_server_die(guild_id):
    from utils.guild_config import set_die
    set_die(guild_id, 37)
    _, body = _render('rolling', guild_id)
    assert 'd37' in body


# ---------------------------------------------------------------------------
# The pager
# ---------------------------------------------------------------------------

def test_view_disables_prev_on_the_first_page(guild_id):
    view = _HelpView(guild_id, 0)
    assert view.prev_button.disabled is True
    assert view.next_button.disabled is False


def test_view_disables_next_on_the_last_page(guild_id):
    view = _HelpView(guild_id, len(_PAGE_KEYS) - 1)
    assert view.prev_button.disabled is False
    assert view.next_button.disabled is True


def test_view_footer_counts_the_pages(guild_id):
    embed = _HelpView(guild_id, 0).build_embed()
    assert f'page 1/{len(_PAGE_KEYS)}' in embed.footer.text


# ---------------------------------------------------------------------------
# Dev commands
# ---------------------------------------------------------------------------

async def test_version_reports_running_version(mock_bot, ctx):
    cog = DevCog(mock_bot)
    await cog.version.callback(cog, ctx)
    assert VERSION in sent_embed(ctx).description


async def test_ping_reports_latency(mock_bot, ctx):
    cog = DevCog(mock_bot)
    await cog.ping.callback(cog, ctx)
    assert 'ms' in sent_embed(ctx).description


# ---------------------------------------------------------------------------
# Documentation coverage — the drift guards
# ---------------------------------------------------------------------------

def _all_cog_modules() -> list[str]:
    return [
        f'cogs.{p.stem}' for p in sorted(Path('cogs').glob('*.py'))
        if p.stem != '__init__'
    ]


def _cog_classes():
    """Every Cog class defined in cogs/, instantiated with a mock bot.

    Cog classes are inspected directly rather than loaded into a Bot: loading
    extensions mutates shared command state and leaks into other test modules.
    """
    import importlib
    import inspect
    from unittest.mock import MagicMock

    from discord.ext import commands as dcommands

    for module_name in _all_cog_modules():
        module = importlib.import_module(module_name)
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, dcommands.Cog)
                and obj is not dcommands.Cog
                and obj.__module__ == module.__name__
            ):
                yield obj(MagicMock())


def _visible_commands() -> list[tuple[str, tuple]]:
    """Every non-hidden command and subcommand, as 'name' or 'group sub'."""
    from discord.ext import commands as dcommands

    def walk(cmds, parents: tuple[tuple[str, ...], ...] = ()):
        """Yield (display name, accepted spellings) for each command.

        A subcommand must be named in full ('!config die'), under the group's
        own name or any of its aliases — naming only the group is not enough.
        """
        for cmd in cmds:
            if getattr(cmd, 'hidden', False):
                continue
            spellings = parents + ((cmd.name, *cmd.aliases),)
            display = ' '.join(options[0] for options in spellings)
            yield display, spellings
            if isinstance(cmd, dcommands.Group):
                yield from walk(cmd.commands, spellings)

    names: dict[str, tuple] = {}
    for cog in _cog_classes():
        names.update(walk(cog.get_commands()))
    return sorted(names.items())


def _all_command_names() -> set[str]:
    """Command names plus aliases, hidden ones and subcommands included."""
    from discord.ext import commands as dcommands

    found: set[str] = set()

    def collect(cmds):
        for cmd in cmds:
            found.add(cmd.name)
            found.update(cmd.aliases)
            if isinstance(cmd, dcommands.Group):
                collect(cmd.commands)

    for cog in _cog_classes():
        collect(cog.get_commands())
    return found


def _rendered_help() -> str:
    """Every help page as the user sees it.

    Rendered for both roll systems, because the rolling page swaps one note
    depending on the server's system — a command named in only one branch
    would otherwise slip past the coverage check.
    """
    from utils.guild_config import set_system

    standard_guild, wod_guild_id = 0, 1
    set_system(wod_guild_id, 'wod')

    parts: list[str] = []
    for guild_id in (standard_guild, wod_guild_id):
        for key in _PAGE_KEYS:
            title, body = _render(key, guild_id)
            parts.append(title)
            parts.append(body)
    return '\n'.join(parts)


def _mentions(text: str, spellings: tuple) -> bool:
    """True if the text names this command, group aliases accepted."""
    for combination in itertools.product(*spellings):
        pattern = re.escape(PREFIX) + r'\s+'.join(
            re.escape(part) for part in combination
        ) + r'\b'
        if re.search(pattern, text):
            return True
    return False


def test_there_are_commands_to_check():
    """A broken discovery helper would make every coverage test vacuous."""
    assert len(_visible_commands()) >= 5


def test_help_pages_mention_every_visible_command():
    text = _rendered_help()
    missing = [name for name, spell in _visible_commands() if not _mentions(text, spell)]
    assert not missing, f'commands missing from {PREFIX}help pages: {missing}'


def test_help_md_mentions_every_visible_command():
    md = Path('help.md').read_text(encoding='utf-8')
    missing = [name for name, spell in _visible_commands() if not _mentions(md, spell)]
    assert not missing, f'commands missing from help.md: {missing}'


def test_features_md_mentions_every_visible_command():
    """FEATURES.md is the always-current feature list — enforced, not promised."""
    md = Path('FEATURES.md').read_text(encoding='utf-8')
    missing = [name for name, spell in _visible_commands() if not _mentions(md, spell)]
    assert not missing, f'commands missing from FEATURES.md: {missing}'


@pytest.mark.parametrize('source', ['pages', 'help.md', 'FEATURES.md'])
def test_documentation_has_no_stale_commands(source):
    """Every prefixed command named in the docs still exists."""
    text = _rendered_help() if source == 'pages' else Path(source).read_text(encoding='utf-8')
    real = _all_command_names()
    named = set(re.findall(re.escape(PREFIX) + r'([a-z]+)', text))
    assert not named - real, f'{source} names commands that do not exist: {sorted(named - real)}'


def test_every_section_page_is_listed_in_the_overview():
    """!help <section> must accept every page key the overview advertises."""
    _, overview = _render('__overview__', 0)
    for key in _PAGE_KEYS:
        if key == '__overview__':
            continue
        assert f'`{key}`' in overview, f'{key} page is not listed in the overview'
