from __future__ import annotations

import discord
from discord.ext import commands

from utils.config import AUTO_JOIN, AUTO_LEAVE
from utils.guild_config import get_all_settings, get_locale, reset_setting, set_locale, set_setting
from utils.i18n import supported_locales, t
from utils.message import MessageWriter

# Keys that can be toggled, with display labels
_BOOL_SETTINGS: dict[str, str] = {
    'auto_join': 'Auto-join (join when first person enters a channel)',
    'auto_leave': 'Auto-leave (leave when last person exits the channel)',
}

_GLOBAL_DEFAULTS: dict[str, bool] = {
    'auto_join': AUTO_JOIN,
    'auto_leave': AUTO_LEAVE,
}


def _format_bool(value: bool) -> str:
    return '✅ Enabled' if value else '❌ Disabled'


def _settings_embed(guild_id: int, guild_name: str) -> discord.Embed:
    effective = get_all_settings(guild_id)
    lines = []
    for key, label in _BOOL_SETTINGS.items():
        value = effective[key]
        default = _GLOBAL_DEFAULTS[key]
        override_note = '' if value == default else ' *(overridden)*'
        lines.append(f'**{key}** — {_format_bool(value)}{override_note}\n*{label}*')

    locale = get_locale(guild_id)
    lines.append(f'**locale** — `{locale}`\n*Display language for bot messages*')

    return MessageWriter.info(t('settings.title', guild_id, guild=guild_name), '\n\n'.join(lines))


class SettingsCog(commands.Cog, name='Settings'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False
        if isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.manage_guild:
            return True
        return await self.bot.is_owner(ctx.author)

    @commands.hybrid_group(name='settings', aliases=['config'], invoke_without_command=True)
    async def settings(self, ctx: commands.Context) -> None:
        """Show or change per-server bot settings (admins only)."""
        await ctx.send(embed=_settings_embed(ctx.guild.id, ctx.guild.name))

    @settings.command(name='set')
    async def settings_set(self, ctx: commands.Context, key: str, value: bool) -> None:
        """Set a per-server setting. Keys: auto_join, auto_leave."""
        guild_id = ctx.guild.id
        key = key.lower()
        if key not in _BOOL_SETTINGS:
            valid = ', '.join(f'`{k}`' for k in _BOOL_SETTINGS)
            await ctx.send(embed=MessageWriter.error(
                t('settings.unknown_key', guild_id, key=key),
                t('settings.unknown_key_hint', guild_id, valid=valid),
            ))
            return
        set_setting(guild_id, key, value)
        await ctx.send(embed=MessageWriter.success(
            t('settings.set_done', guild_id, key=key, value=_format_bool(value)),
        ))

    @settings.command(name='reset')
    async def settings_reset(self, ctx: commands.Context, key: str) -> None:
        """Reset a per-server setting back to the global default."""
        guild_id = ctx.guild.id
        key = key.lower()
        if key not in _BOOL_SETTINGS:
            valid = ', '.join(f'`{k}`' for k in _BOOL_SETTINGS)
            await ctx.send(embed=MessageWriter.error(
                t('settings.unknown_key', guild_id, key=key),
                t('settings.unknown_key_hint', guild_id, valid=valid),
            ))
            return
        reset_setting(guild_id, key)
        default = _GLOBAL_DEFAULTS[key]
        await ctx.send(embed=MessageWriter.success(
            t('settings.reset_done', guild_id, key=key, value=_format_bool(default)),
        ))

    @settings.command(name='locale')
    async def settings_locale(self, ctx: commands.Context, code: str = '') -> None:
        """Set or show the display language. Available: run with no argument to see list."""
        guild_id = ctx.guild.id
        if not code:
            current = get_locale(guild_id)
            available = ', '.join(f'`{loc}`' for loc in supported_locales())
            await ctx.send(embed=MessageWriter.info(
                t('settings.locale_current', guild_id, locale=current),
                f'Available: {available}',
            ))
            return

        code = code.lower().strip()
        available = supported_locales()
        if code not in available:
            await ctx.send(embed=MessageWriter.error(
                t('settings.locale_invalid', guild_id, locale=code),
                t('settings.locale_invalid_hint', guild_id, available=', '.join(f'`{l}`' for l in available)),
            ))
            return

        set_locale(guild_id, code)
        # Respond in the NEW locale
        await ctx.send(embed=MessageWriter.success(
            t('settings.locale_set', guild_id, locale=code),
        ))

    @settings.command(name='show')
    async def settings_show(self, ctx: commands.Context) -> None:
        """Show current per-server settings."""
        await ctx.send(embed=_settings_embed(ctx.guild.id, ctx.guild.name))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SettingsCog(bot))
