import importlib
import logging
import sys

import discord
from discord.ext import commands

from utils.i18n import t

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
    'utils.i18n',
    'utils.guild_config',
    'utils.notifier',
]


class DevCog(commands.Cog, name='Dev'):
    """Owner-only: reload, restart, sync, status. Prefix commands only."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

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
            await ctx.send(t('dev.reload_success', ext=ext))
            log.info('Reloaded extension: %s (requested by %s)', ext, ctx.author)
        except Exception as exc:
            await ctx.send(t('dev.reload_failed', ext=ext, exc=exc))
            log.error('Failed to reload %s: %s', ext, exc)

    @commands.command(name='restart', hidden=True)
    async def restart_bot(self, ctx: commands.Context) -> None:
        await ctx.send(t('dev.restarting'))
        log.info('Restart requested by %s', ctx.author)
        await self.bot.close()

    @commands.command(name='sync', hidden=True)
    async def sync_tree(self, ctx: commands.Context, guild_id: int | None = None) -> None:
        if guild_id:
            guild = discord.Object(id=guild_id)
            self.bot.tree.copy_global_to(guild=guild)
            synced = await self.bot.tree.sync(guild=guild)
            await ctx.send(t('dev.sync_guild', count=len(synced), guild_id=guild_id))
        else:
            synced = await self.bot.tree.sync()
            await ctx.send(t('dev.sync_global', count=len(synced)))
        log.info('Slash tree synced by %s', ctx.author)

    @commands.command(name='status', hidden=True)
    async def status(self, ctx: commands.Context) -> None:
        await ctx.send(t(
            'dev.status',
            user=self.bot.user,
            voice=len(self.bot.voice_clients),
            guilds=len(self.bot.guilds),
            cogs=', '.join(self.bot.cogs),
        ))

    @commands.command(name='cogs', hidden=True)
    async def list_cogs(self, ctx: commands.Context) -> None:
        loaded = list(self.bot.extensions)
        await ctx.send(t('dev.cogs_header') + '\n' + '\n'.join(f'• `{c}`' for c in loaded))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DevCog(bot))
