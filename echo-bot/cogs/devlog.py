from __future__ import annotations

import logging

import discord
from discord.ext import commands

from utils import devlog
from utils.i18n import t
from utils.message import MessageWriter

log = logging.getLogger(__name__)


class DevlogCog(commands.Cog, name='Devlog'):
    """Per-server dev log: forward this server's errors to a channel or a DM.

    Manage Server can turn it on for their server; `all` (errors not tied to
    any server) and DM-everything are bot-owner only.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name='devlog')
    async def devlog_cmd(self, ctx: commands.Context, action: str = '', scope: str = '') -> None:
        """!devlog [here|dm|off|test] [all]"""
        action, scope = action.lower(), scope.lower()
        if scope not in ('', 'all'):
            await ctx.send(embed=MessageWriter.error(t('devlog.usage_title'), t('devlog.usage')))
            return
        include_all = scope == 'all'
        is_owner = await self.bot.is_owner(ctx.author)

        if ctx.guild is None:
            await self._handle_dm(ctx, action, is_owner)
            return

        gid = ctx.guild.id
        can_manage = is_owner or (
            isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.manage_guild
        )
        if action and not can_manage:
            await ctx.send(embed=MessageWriter.error(t('devlog.no_permission', gid)))
            return
        if include_all and not is_owner:
            await ctx.send(embed=MessageWriter.error(t('devlog.all_owner_only', gid)))
            return

        if action == '':
            await ctx.send(embed=MessageWriter.info(t('devlog.status_title', gid), self._status(gid)))
        elif action == 'here':
            devlog.set_guild_target(gid, 'channel', ctx.channel.id, include_all)
            key = 'devlog.on_channel_all' if include_all else 'devlog.on_channel'
            await ctx.send(embed=MessageWriter.success(t('devlog.on_title', gid), t(key, gid)))
        elif action == 'dm':
            try:
                await ctx.author.send(embed=MessageWriter.success(
                    t('devlog.on_title', gid), t('devlog.dm_welcome', gid, guild=ctx.guild.name),
                ))
            except discord.HTTPException:
                await ctx.send(embed=MessageWriter.error(t('devlog.dm_blocked', gid)))
                return
            devlog.set_guild_target(gid, 'dm', ctx.author.id, include_all)
            await ctx.send(embed=MessageWriter.success(t('devlog.on_title', gid), t('devlog.on_dm', gid)))
        elif action == 'off':
            if devlog.clear_guild_target(gid):
                await ctx.send(embed=MessageWriter.success(t('devlog.off', gid)))
            else:
                await ctx.send(embed=MessageWriter.info(t('devlog.already_off', gid)))
        elif action == 'test':
            await self._send_test(ctx)
        else:
            await ctx.send(embed=MessageWriter.error(t('devlog.usage_title', gid), t('devlog.usage', gid)))

    async def _handle_dm(self, ctx: commands.Context, action: str, is_owner: bool) -> None:
        """In a DM there is no server: `here` subscribes the owner to everything."""
        if action and not is_owner:
            await ctx.send(embed=MessageWriter.error(t('devlog.dm_owner_only')))
            return
        if action == '':
            owner_dm = devlog.get_owner_dm()
            key = 'devlog.dm_status_on' if owner_dm == ctx.author.id else 'devlog.dm_status_off'
            await ctx.send(embed=MessageWriter.info(t('devlog.status_title'), t(key)))
        elif action in ('here', 'dm'):
            devlog.set_owner_dm(ctx.author.id)
            await ctx.send(embed=MessageWriter.success(t('devlog.on_title'), t('devlog.on_owner_dm')))
        elif action == 'off':
            devlog.set_owner_dm(None)
            await ctx.send(embed=MessageWriter.success(t('devlog.off_owner_dm')))
        elif action == 'test':
            await self._send_test(ctx)
        else:
            await ctx.send(embed=MessageWriter.error(t('devlog.usage_title'), t('devlog.usage')))

    async def _send_test(self, ctx: commands.Context) -> None:
        gid = ctx.guild.id if ctx.guild else 0
        log.warning('Dev log test requested by %s', ctx.author)
        await ctx.send(embed=MessageWriter.info(t('devlog.test_sent', gid)))

    @staticmethod
    def _status(guild_id: int) -> str:
        target = devlog.get_guild_target(guild_id)
        if not target:
            return t('devlog.status_off', guild_id)
        where = f'<#{target["id"]}>' if target['kind'] == 'channel' else f'<@{target["id"]}> (DM)'
        key = 'devlog.status_on_all' if target.get('all') else 'devlog.status_on'
        return t(key, guild_id, where=where)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DevlogCog(bot))
