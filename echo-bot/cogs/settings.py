from __future__ import annotations

from typing import Any

import discord
from discord.ext import commands

from utils.config import AUTO_JOIN, AUTO_LEAVE
from utils.guild_config import (
    get_all_settings,
    get_locale,
    get_voice_language,
    reset_setting,
    set_locale,
    set_setting,
    set_voice_language,
)
from utils.i18n import supported_locales, t
from utils.message import MessageWriter

# ---------------------------------------------------------------------------
# Setting registries
# ---------------------------------------------------------------------------

# Toggle settings (true/false)
_BOOL_SETTINGS: dict[str, str] = {
    'auto_join': 'Auto-join (join when first person enters a channel)',
    'auto_leave': 'Auto-leave (leave when last person exits the channel)',
    'notify_write': 'Notify write (send a text message for command responses)',
    'notify_say': 'Notify say (speak responses via TTS when bot is in voice)',
}

# String settings managed via dedicated subcommands (shown in settings embed)
_STRING_SETTINGS: dict[str, str] = {
    'locale': 'Display language for bot text messages',
    'voice_language': 'TTS voice language (e.g. en, sr) — empty = use tts_voice setting',
}

# Merged for reset validation
_ALL_RESETTABLE: dict[str, str] = {**_BOOL_SETTINGS, **_STRING_SETTINGS}

_BOOL_DEFAULTS: dict[str, bool] = {
    'auto_join': AUTO_JOIN,
    'auto_leave': AUTO_LEAVE,
    'notify_write': True,
    'notify_say': False,
}

_STRING_DEFAULTS: dict[str, str] = {
    'locale': 'en',
    'voice_language': '',
}

_ALL_DEFAULTS: dict[str, Any] = {**_BOOL_DEFAULTS, **_STRING_DEFAULTS}

# Keep _GLOBAL_DEFAULTS as an alias used in tests / _settings_embed
_GLOBAL_DEFAULTS = _BOOL_DEFAULTS


def _format_bool(value: bool) -> str:
    return '✅ Enabled' if value else '❌ Disabled'


def _format_default(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return _format_bool(value)
    return f'`{value}`' if value else '*(empty)*'


def _settings_embed(guild_id: int, guild_name: str) -> discord.Embed:
    effective = get_all_settings(guild_id)
    lines = []

    for setting_key, label in _BOOL_SETTINGS.items():
        value = effective[setting_key]
        default = _BOOL_DEFAULTS[setting_key]
        override_note = '' if value == default else ' *(overridden)*'
        lines.append(f'**{setting_key}** — {_format_bool(value)}{override_note}\n*{label}*')

    locale = get_locale(guild_id)
    locale_default = _STRING_DEFAULTS['locale']
    locale_note = '' if locale == locale_default else ' *(overridden)*'
    lines.append(f'**locale** — `{locale}`{locale_note}\n*{_STRING_SETTINGS["locale"]}*')

    vl = get_voice_language(guild_id)
    vl_display = f'`{vl}`' if vl else '*(not set)*'
    vl_note = ' *(overridden)*' if vl else ''
    lines.append(f'**voice_language** — {vl_display}{vl_note}\n*{_STRING_SETTINGS["voice_language"]}*')

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
        """Set a toggle setting. Keys: auto_join, auto_leave, notify_write, notify_say."""
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
        """Reset any setting back to its global default."""
        guild_id = ctx.guild.id
        key = key.lower()
        if key not in _ALL_RESETTABLE:
            valid = ', '.join(f'`{k}`' for k in _ALL_RESETTABLE)
            await ctx.send(embed=MessageWriter.error(
                t('settings.unknown_key', guild_id, key=key),
                t('settings.unknown_key_hint', guild_id, valid=valid),
            ))
            return
        reset_setting(guild_id, key)
        default = _ALL_DEFAULTS[key]
        value_str = _format_default(key, default)
        await ctx.send(embed=MessageWriter.success(
            t('settings.reset_done', guild_id, key=key, value=value_str),
        ))

    @settings.command(name='locale', aliases=['language', 'text_language'])
    async def settings_locale(self, ctx: commands.Context, code: str = '') -> None:
        """Set or show the display language. Aliases: language, text_language."""
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
        await ctx.send(embed=MessageWriter.success(
            t('settings.locale_set', guild_id, locale=code),
        ))

    @settings.command(name='voice_language')
    async def settings_voice_language(self, ctx: commands.Context, code: str = '') -> None:
        """Set or show the TTS voice language. Use a locale prefix like `en` or `sr`."""
        guild_id = ctx.guild.id
        if not code:
            current = get_voice_language(guild_id)
            display = f'`{current}`' if current else '*(not set — using tts_voice setting)*'
            await ctx.send(embed=MessageWriter.info(
                t('settings.voice_language_current', guild_id),
                display,
            ))
            return

        code = code.lower().strip()
        set_voice_language(guild_id, code)
        await ctx.send(embed=MessageWriter.success(
            t('settings.voice_language_set', guild_id, code=code),
        ))

    @settings.command(name='show')
    async def settings_show(self, ctx: commands.Context) -> None:
        """Show current per-server settings."""
        await ctx.send(embed=_settings_embed(ctx.guild.id, ctx.guild.name))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SettingsCog(bot))
