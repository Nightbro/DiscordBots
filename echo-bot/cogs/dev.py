import importlib
import logging
import sys

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

# Modules reloaded before a cog reload so updated utils code takes effect
_UTIL_MODULES = [
    'utils.config',
    'utils.guild_state',
    'utils.persistence',
    'utils.message',
    'utils.reactions',
    'utils.voice',
    'utils.audio',
    'utils.downloader',
]


class DevCog(commands.Cog, name='Dev'):
    """Owner-only: reload, restart, sync, status. Prefix commands only."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # All commands in this cog are owner-only
    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(name='reload', hidden=True)
    async def reload_cog(self, ctx: commands.Context, cog: str) -> None:
        ext = f'cogs.{cog}' if not cog.startswith('cogs.') else cog
        for mod in _UTIL_MODULES:
            if mod in sys.modules:
                importlib.reload(sys.modules[mod])
        try:
            await self.bot.reload_extension(ext)
            await ctx.send(f'✅ Reloaded `{ext}`')
            log.info('Reloaded extension: %s (requested by %s)', ext, ctx.author)
        except Exception as exc:
            await ctx.send(f'❌ Failed to reload `{ext}`:\n```\n{exc}\n```')
            log.error('Failed to reload %s: %s', ext, exc)

    @commands.command(name='restart', hidden=True)
    async def restart_bot(self, ctx: commands.Context) -> None:
        await ctx.send('♻️ Restarting...')
        log.info('Restart requested by %s', ctx.author)
        await self.bot.close()

    @commands.command(name='sync', hidden=True)
    async def sync_tree(self, ctx: commands.Context, guild_id: int | None = None) -> None:
        if guild_id:
            guild = discord.Object(id=guild_id)
            self.bot.tree.copy_global_to(guild=guild)
            synced = await self.bot.tree.sync(guild=guild)
            await ctx.send(f'✅ Synced {len(synced)} commands to guild `{guild_id}`')
        else:
            synced = await self.bot.tree.sync()
            await ctx.send(
                f'✅ Synced {len(synced)} global commands '
                f'(may take up to 1 hour to propagate)'
            )
        log.info('Slash tree synced by %s', ctx.author)

    @commands.command(name='status', hidden=True)
    async def status(self, ctx: commands.Context) -> None:
        lines = [
            f'**{self.bot.user}** — online',
            f'Voice connections: {len(self.bot.voice_clients)}',
            f'Guilds: {len(self.bot.guilds)}',
            f'Cogs: {", ".join(self.bot.cogs)}',
        ]
        await ctx.send('\n'.join(lines))

    @commands.command(name='cogs', hidden=True)
    async def list_cogs(self, ctx: commands.Context) -> None:
        loaded = list(self.bot.extensions)
        await ctx.send('**Loaded extensions:**\n' + '\n'.join(f'• `{c}`' for c in loaded))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DevCog(bot))
