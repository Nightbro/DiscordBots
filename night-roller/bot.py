# SSL fix — must be first, before any other imports
import ssl
import certifi


def _patched_ssl_context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None, **_):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(cafile or certifi.where(), capath, cadata)
    return ctx


ssl.create_default_context = _patched_ssl_context

import asyncio
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands

from utils.config import BOT_NAME, LOGS_DIR, PREFIX, VERSION

# --- Logging ---
# One log file per process start, named with the start timestamp.
_fmt = logging.Formatter(
    fmt='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
_run_stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
_file_handler = RotatingFileHandler(
    LOGS_DIR / f'night_roller_{_run_stamp}.log',
    maxBytes=2 * 1024 * 1024,
    backupCount=3,
    encoding='utf-8',
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(_fmt)

_console = logging.StreamHandler()
_console.setLevel(logging.INFO)
_console.setFormatter(_fmt)

logging.basicConfig(level=logging.DEBUG, handlers=[_file_handler, _console])
logging.getLogger('discord').setLevel(logging.WARNING)
logging.getLogger('discord.http').setLevel(logging.WARNING)

log = logging.getLogger('night-roller')

# --- Bot ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

_COGS = [
    'cogs.roll',
    'cogs.help',
    'cogs.dev',
]


@bot.event
async def on_ready():
    log.info('Logged in as %s (ID: %s)', bot.user, bot.user.id)
    log.info('%s %s is ready.', BOT_NAME, VERSION)
    dev_guild_id = os.getenv('DEV_GUILD_ID')
    if dev_guild_id:
        guild = discord.Object(id=int(dev_guild_id))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        log.info('Slash commands synced to dev guild %s', dev_guild_id)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
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
