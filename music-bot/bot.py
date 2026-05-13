# ── SSL fix: must be FIRST before any other imports ──────────────────────────
import ssl
import certifi

def _patched_ssl_context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None, **_):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(cafile or certifi.where(), capath, cadata)
    return ctx

ssl.create_default_context = _patched_ssl_context
# ─────────────────────────────────────────────────────────────────────────────

import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands

from utils.config import LOGS_DIR, DOWNLOADS_DIR  # triggers load_dotenv + dir creation

# --- Logging ---
_fmt = logging.Formatter(
    fmt='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
_file_handler = RotatingFileHandler(
    LOGS_DIR / 'music-bot.log',
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

log = logging.getLogger('music-bot')

# --- Bot ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
bot.guild_states = {}


@bot.event
async def on_ready():
    log.info('Logged in as %s (ID: %s)', bot.user, bot.user.id)
    log.info('Download cache: %s', DOWNLOADS_DIR)
    log.info('Log file: %s', LOGS_DIR / 'music-bot.log')
    log.info('Bot is ready.')


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'Missing argument: `{error.param.name}`')
        return
    log.error(
        'Unhandled command error — command: %s | user: %s | guild: %s | error: %s',
        ctx.command, ctx.author, ctx.guild.id, error,
        exc_info=error,
    )


@bot.event
async def on_message(message):
    await bot.process_commands(message)


# --- Run ---
async def main():
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise ValueError('DISCORD_TOKEN not set in .env file')
    async with bot:
        await bot.load_extension('cogs.music')
        await bot.load_extension('cogs.intros')
        await bot.load_extension('cogs.soundboard')
        await bot.start(token)


asyncio.run(main())
