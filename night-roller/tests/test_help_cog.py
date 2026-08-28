from cogs.dev import DevCog
from cogs.help import HelpCog
from conftest import sent_embed
from utils.config import BOT_NAME, PREFIX, VERSION


async def test_help_lists_roll_command(mock_bot, ctx):
    cog = HelpCog(mock_bot)
    await cog.help_cmd.callback(cog, ctx)
    embed = sent_embed(ctx)
    assert BOT_NAME in embed.title
    assert f'{PREFIX}roll' in embed.description


async def test_help_documents_advantage(mock_bot, ctx):
    cog = HelpCog(mock_bot)
    await cog.help_cmd.callback(cog, ctx)
    assert 'advantage' in sent_embed(ctx).description


async def test_version_reports_running_version(mock_bot, ctx):
    cog = DevCog(mock_bot)
    await cog.version.callback(cog, ctx)
    assert VERSION in sent_embed(ctx).description


async def test_ping_reports_latency(mock_bot, ctx):
    cog = DevCog(mock_bot)
    await cog.ping.callback(cog, ctx)
    assert 'ms' in sent_embed(ctx).description
