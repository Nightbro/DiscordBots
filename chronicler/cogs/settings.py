from __future__ import annotations

import logging

from discord.ext import commands

from utils.config import PREFIX
from utils.guild_config import (
    SETTING_ERROR_TITLE,
    SettingError,
    get_all_settings,
    reset_guild,
    set_die,
    set_difficulty,
    set_subtract_ones,
    set_system,
)
from utils.message import MessageWriter

log = logging.getLogger(__name__)

_ON = {'on', 'true', 'yes', 'enable', 'enabled', '1'}
_OFF = {'off', 'false', 'no', 'disable', 'disabled', '0'}


class SettingsCog(commands.Cog, name='Settings'):
    """Per-server roll settings. Requires Manage Server."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        # Settings are server-wide, so they need a server and a manager.
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    @commands.hybrid_group(name='config', aliases=['settings'], invoke_without_command=True)
    @commands.has_guild_permissions(manage_guild=True)
    async def config(self, ctx: commands.Context) -> None:
        """Show this server's roll settings."""
        await self._show(ctx)

    async def _show(self, ctx: commands.Context) -> None:
        settings = get_all_settings(ctx.guild.id)
        await ctx.send(embed=MessageWriter.config_card(settings, PREFIX))

    @config.command(name='show')
    @commands.has_guild_permissions(manage_guild=True)
    async def config_show(self, ctx: commands.Context) -> None:
        """Show this server's roll settings."""
        await self._show(ctx)

    @config.command(name='system')
    @commands.has_guild_permissions(manage_guild=True)
    async def config_system(self, ctx: commands.Context, system: str) -> None:
        """Set the roll system: standard or wod."""
        try:
            chosen = set_system(ctx.guild.id, system)
        except SettingError as exc:
            await ctx.send(embed=MessageWriter.error(SETTING_ERROR_TITLE, str(exc)))
            return
        log.info('Guild %s system → %s', ctx.guild.id, chosen)
        await self._show(ctx)

    @config.command(name='die', aliases=['dice'])
    @commands.has_guild_permissions(manage_guild=True)
    async def config_die(self, ctx: commands.Context, sides: int) -> None:
        """Set the default die used by pool rolls like !roll 5."""
        try:
            set_die(ctx.guild.id, sides)
        except SettingError as exc:
            await ctx.send(embed=MessageWriter.error(SETTING_ERROR_TITLE, str(exc)))
            return
        await self._show(ctx)

    @config.command(name='difficulty', aliases=['diff'])
    @commands.has_guild_permissions(manage_guild=True)
    async def config_difficulty(self, ctx: commands.Context, difficulty: int) -> None:
        """Set the default success target."""
        try:
            set_difficulty(ctx.guild.id, difficulty)
        except SettingError as exc:
            await ctx.send(embed=MessageWriter.error(SETTING_ERROR_TITLE, str(exc)))
            return
        await self._show(ctx)

    @config.command(name='ones')
    @commands.has_guild_permissions(manage_guild=True)
    async def config_ones(self, ctx: commands.Context, state: str) -> None:
        """Turn the botch rule (each 1 cancels a success) on or off."""
        value = state.strip().lower()
        if value in _ON:
            set_subtract_ones(ctx.guild.id, True)
        elif value in _OFF:
            set_subtract_ones(ctx.guild.id, False)
        else:
            await ctx.send(embed=MessageWriter.error(
                SETTING_ERROR_TITLE, 'Use `on` or `off`.'
            ))
            return
        await self._show(ctx)

    @config.command(name='reset')
    @commands.has_guild_permissions(manage_guild=True)
    async def config_reset(self, ctx: commands.Context) -> None:
        """Drop every override and go back to the global defaults."""
        reset_guild(ctx.guild.id)
        log.info('Guild %s settings reset', ctx.guild.id)
        await self._show(ctx)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SettingsCog(bot))
