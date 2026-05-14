# SSL fix — must be first, before any other imports
import ssl
import certifi

def _patched_ssl_context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None, **_):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(cafile or certifi.where(), capath, cadata)
    return ctx

ssl.create_default_context = _patched_ssl_context

import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands

from utils.config import BOT_NAME, PREFIX, LOGS_DIR, DOWNLOADS_DIR
from utils.guild_config import get_auto_join, get_auto_leave
from utils.guild_state import GuildState
from utils.voice import VoiceStreamer

# --- Logging ---
_fmt = logging.Formatter(
    fmt='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
_file_handler = RotatingFileHandler(
    LOGS_DIR / f'{BOT_NAME.lower()}.log',
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding='utf-8',
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(_fmt)

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(_fmt)

logging.basicConfig(level=logging.DEBUG, handlers=[_file_handler, _console_handler])
logging.getLogger('discord').setLevel(logging.WARNING)
logging.getLogger('discord.http').setLevel(logging.WARNING)

log = logging.getLogger(BOT_NAME.lower())

# --- Bot ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

_guild_states: dict[int, GuildState] = {}


def get_guild_state(guild_id: int) -> GuildState:
    if guild_id not in _guild_states:
        _guild_states[guild_id] = GuildState()
    return _guild_states[guild_id]


bot.get_guild_state = get_guild_state  # type: ignore[attr-defined]

_COGS = [
    'cogs.help',
    'cogs.settings',
    'cogs.music',
    'cogs.intros',
    'cogs.soundboard',
    'cogs.tts',
    'cogs.listener',
    'cogs.dev',
]


@bot.event
async def on_ready():
    log.info('Logged in as %s (ID: %s)', bot.user, bot.user.id)
    log.info('Data dir: %s', DOWNLOADS_DIR.parent)
    dev_guild_id = os.getenv('DEV_GUILD_ID')
    if dev_guild_id:
        guild = discord.Object(id=int(dev_guild_id))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        log.info('Slash commands synced to dev guild %s', dev_guild_id)
    log.info('%s is ready.', BOT_NAME)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'Missing argument: `{error.param.name}`')
        return
    if isinstance(error, (commands.NotOwner, commands.CheckFailure)):
        await ctx.send('You do not have permission to use this command.')
        return
    log.error(
        'Unhandled command error — command: %s | user: %s | guild: %s | error: %s',
        ctx.command,
        ctx.author,
        ctx.guild.id if ctx.guild else 'DM',
        error,
        exc_info=error,
    )


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    if member.bot:
        return

    guild_id = member.guild.id

    # Auto-leave: member left a channel the bot is in — check if it's now empty
    if get_auto_leave(guild_id):
        state = _guild_states.get(guild_id)
        if state:
            vc = state.voice_client
            if vc and vc.channel and before.channel and before.channel.id == vc.channel.id:
                await VoiceStreamer.auto_leave_if_empty(bot, guild_id, vc.channel)

    # Auto-join: member joined a channel and bot isn't in any channel for this guild
    if get_auto_join(guild_id) and after.channel is not None and before.channel != after.channel:
        state = _guild_states.get(guild_id)
        if state is None or state.voice_client is None:
            await VoiceStreamer(bot, guild_id).join(after.channel)


@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)


# --- Run ---
async def main():
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise ValueError('DISCORD_TOKEN not set in .env')
    owner_id = os.getenv('OWNER_ID')
    if owner_id:
        bot.owner_id = int(owner_id)
    async with bot:
        for cog in _COGS:
            await bot.load_extension(cog)
            log.info('Loaded cog: %s', cog)
        await bot.start(token)


asyncio.run(main())
