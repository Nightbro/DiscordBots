import pytest
from unittest.mock import AsyncMock, MagicMock

from cogs.help import HelpCog, _PAGE_KEYS, _HelpView, _build_embed

_SECTION_KEYS = [k for k in _PAGE_KEYS if k != '__overview__']


# ---------------------------------------------------------------------------
# _build_embed
# ---------------------------------------------------------------------------

def test_overview_embed_title():
    embed = _build_embed('__overview__', 1, len(_PAGE_KEYS), guild_id=0)
    assert 'Echo' in embed.title or 'Help' in embed.title


def test_section_embed_title():
    embed = _build_embed('music', 2, len(_PAGE_KEYS), guild_id=0)
    assert 'Music' in embed.title or 'music' in embed.title


def test_embed_footer_has_page_number():
    embed = _build_embed('__overview__', 1, len(_PAGE_KEYS), guild_id=0)
    assert f'1/{len(_PAGE_KEYS)}' in embed.footer.text


def test_all_sections_have_embeds():
    for key in _PAGE_KEYS:
        embed = _build_embed(key, 1, len(_PAGE_KEYS), guild_id=0)
        assert embed.title
        assert embed.description


# ---------------------------------------------------------------------------
# _HelpView
# ---------------------------------------------------------------------------

def test_view_starts_at_given_index():
    view = _HelpView(start_index=2, guild_id=0)
    embed = view.build_embed()
    assert embed  # just ensure it builds without error


def test_view_prev_disabled_at_start():
    view = _HelpView(start_index=0, guild_id=0)
    assert view.prev_button.disabled is True
    assert view.next_button.disabled is False


def test_view_next_disabled_at_end():
    view = _HelpView(start_index=len(_PAGE_KEYS) - 1, guild_id=0)
    assert view.next_button.disabled is True


def test_view_both_enabled_in_middle():
    view = _HelpView(start_index=2, guild_id=0)
    assert view.prev_button.disabled is False
    assert view.next_button.disabled is False


# ---------------------------------------------------------------------------
# HelpCog.help_cmd
# ---------------------------------------------------------------------------

def _cog(mock_bot) -> HelpCog:
    return HelpCog(mock_bot)


async def test_help_cmd_no_section_shows_overview(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.help_cmd.callback(cog, ctx, section='')
    ctx.send.assert_awaited_once()
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'Help' in embed.title


async def test_help_cmd_music_section(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.help_cmd.callback(cog, ctx, section='music')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'Music' in embed.title or 'music' in embed.title.lower()


async def test_help_cmd_unknown_section_falls_back_to_overview(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.help_cmd.callback(cog, ctx, section='unknown')
    embed = ctx.send.call_args.kwargs.get('embed') or ctx.send.call_args.args[0]
    assert 'Help' in embed.title


async def test_help_cmd_sends_view(mock_bot, ctx):
    cog = _cog(mock_bot)
    await cog.help_cmd.callback(cog, ctx, section='')
    call_kwargs = ctx.send.call_args.kwargs
    assert 'view' in call_kwargs
    assert isinstance(call_kwargs['view'], _HelpView)


@pytest.mark.parametrize('section', _SECTION_KEYS)
async def test_help_cmd_all_valid_sections(mock_bot, ctx, section):
    cog = _cog(mock_bot)
    await cog.help_cmd.callback(cog, ctx, section=section)
    ctx.send.assert_awaited_once()


# ---------------------------------------------------------------------------
# Help coverage — guards against help drifting from the real command set
# ---------------------------------------------------------------------------

def _all_cog_modules() -> list[str]:
    from pathlib import Path
    return [
        f'cogs.{p.stem}' for p in sorted(Path('cogs').glob('*.py'))
        if p.stem != '__init__'
    ]


def _visible_commands() -> list[str]:
    """Every non-hidden command and subcommand, as 'name' or 'group sub'.

    Cog classes are inspected directly rather than loaded into a Bot: loading
    extensions mutates shared command state and leaks into other test modules.
    """
    import importlib
    import inspect
    from unittest.mock import MagicMock

    from discord.ext import commands as dcommands

    def walk(cmds, parents: tuple[tuple[str, ...], ...] = ()):
        """Yield (display name, accepted spellings) for each command.

        A subcommand must be named in full ('!lib info'), under the group's own
        name or any of its aliases — mentioning only the group is not enough.
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
    for module_name in _all_cog_modules():
        module = importlib.import_module(module_name)
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, dcommands.Cog)
                and obj is not dcommands.Cog
                and obj.__module__ == module.__name__
            ):
                names.update(walk(obj(MagicMock()).get_commands()))
    return sorted(names.items())


def _all_command_names() -> set[str]:
    """Command names plus aliases, hidden ones included."""
    import importlib
    import inspect
    from unittest.mock import MagicMock

    from discord.ext import commands as dcommands

    found: set[str] = set()
    for module_name in _all_cog_modules():
        module = importlib.import_module(module_name)
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, dcommands.Cog)
                and obj is not dcommands.Cog
                and obj.__module__ == module.__name__
            ):
                for cmd in obj(MagicMock()).get_commands():
                    found.add(cmd.name)
                    found.update(cmd.aliases)
    return found


def _rendered_help() -> str:
    from cogs.help import _PAGE_KEYS
    from utils.i18n import t
    parts = []
    for key in _PAGE_KEYS:
        name = 'overview' if key == '__overview__' else key
        parts.append(t(f'help.{name}.title', bot='Echo', prefix='!'))
        parts.append(t(f'help.{name}.body', bot='Echo', prefix='!'))
    return '\n'.join(parts)


def _mentions(text: str, spellings: tuple) -> bool:
    """True if the help text names this command, group aliases accepted."""
    import itertools
    import re
    for combination in itertools.product(*spellings):
        pattern = '!' + r'\s+'.join(re.escape(part) for part in combination) + r'\b'
        if re.search(pattern, text):
            return True
    return False


def test_help_pages_mention_every_visible_command():
    text = _rendered_help()
    missing = [name for name, spell in _visible_commands() if not _mentions(text, spell)]
    assert not missing, f'commands missing from !help pages: {missing}'


def test_help_md_mentions_every_visible_command():
    md = open('help.md', encoding='utf-8').read()
    missing = [name for name, spell in _visible_commands() if not _mentions(md, spell)]
    assert not missing, f'commands missing from help.md: {missing}'


def test_help_pages_have_no_stale_commands():
    """Every !command named in the help pages still exists."""
    import re
    real = _all_command_names()
    named = set(re.findall(r'!([a-z]+)', _rendered_help()))
    assert not named - real, f'help names commands that do not exist: {sorted(named - real)}'


def test_every_section_page_is_reachable_by_name():
    """!help <section> must accept every page key shown in the overview."""
    from cogs.help import _PAGE_KEYS
    from utils.i18n import t
    overview = t('help.overview.body', bot='Echo', prefix='!')
    for key in _PAGE_KEYS:
        if key == '__overview__':
            continue
        assert f'`{key}`' in overview, f'{key} page is not listed in the overview'


@pytest.mark.parametrize('locale_file', ['locales/banners/en.yaml', 'locales/banners/sr.yaml'])
def test_both_locales_have_every_help_page(locale_file):
    import yaml
    from cogs.help import _PAGE_KEYS
    data = yaml.safe_load(open(locale_file, encoding='utf-8'))['help']
    for key in _PAGE_KEYS:
        name = 'overview' if key == '__overview__' else key
        assert name in data, f'{locale_file} is missing the {name} page'
        assert data[name].get('body'), f'{locale_file}: {name} page has no body'
