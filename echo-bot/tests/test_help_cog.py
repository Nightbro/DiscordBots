import pytest
from unittest.mock import AsyncMock, MagicMock

from cogs.help import HelpCog, _SECTIONS, _PAGE_KEYS, _HelpView, _build_embed


# ---------------------------------------------------------------------------
# _build_embed
# ---------------------------------------------------------------------------

def test_overview_embed_title():
    embed = _build_embed('__overview__', 1, 6)
    assert 'Echo' in embed.title or 'Help' in embed.title


def test_section_embed_title():
    embed = _build_embed('music', 2, 6)
    assert 'Music' in embed.title


def test_embed_footer_has_page_number():
    embed = _build_embed('__overview__', 1, 6)
    assert '1/6' in embed.footer.text


def test_all_sections_have_embeds():
    for key in _PAGE_KEYS:
        embed = _build_embed(key, 1, len(_PAGE_KEYS))
        assert embed.title
        assert embed.description


# ---------------------------------------------------------------------------
# _HelpView
# ---------------------------------------------------------------------------

def test_view_starts_at_given_index():
    view = _HelpView(start_index=2)
    embed = view.build_embed()
    assert embed  # just ensure it builds without error


def test_view_prev_disabled_at_start():
    view = _HelpView(start_index=0)
    assert view.prev_button.disabled is True
    assert view.next_button.disabled is False


def test_view_next_disabled_at_end():
    view = _HelpView(start_index=len(_PAGE_KEYS) - 1)
    assert view.next_button.disabled is True


def test_view_both_enabled_in_middle():
    view = _HelpView(start_index=2)
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
    assert 'Music' in embed.title


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


@pytest.mark.parametrize('section', list(_SECTIONS.keys()))
async def test_help_cmd_all_valid_sections(mock_bot, ctx, section):
    cog = _cog(mock_bot)
    await cog.help_cmd.callback(cog, ctx, section=section)
    ctx.send.assert_awaited_once()
