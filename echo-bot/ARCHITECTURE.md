# Echo Bot — Architecture

> **Session start rule:** Read this file at the beginning of every session before touching any code.

## Overview

Echo is a Discord bot for server audio interaction: music playback, soundboard, per-user intro sounds, and TTS voice output (with voice listening as a future capability). It lives at `echo-bot/` inside the `DiscordBots` monorepo.

Echo supports both `!` prefix commands and `/` slash commands via discord.py hybrid commands. A single command definition covers both surfaces. It runs on a Raspberry Pi via PM2.

---

## Folder Structure

```
echo-bot/
├── bot.py                    # Entry point: bot init, cog loading, event hooks
├── config.yaml               # All locality settings (name, prefix, colors, emojis, timeouts)
├── pm2.config.js             # PM2 process manager config for auto-restart
├── .env                      # Secrets only: DISCORD_TOKEN, API keys
├── .env.example              # Committed template with empty values
├── requirements.txt
├── pytest.ini
├── ARCHITECTURE.md           # This file
│
├── cogs/                     # Feature cogs — one per domain
│   ├── __init__.py
│   ├── music.py              # Playback: YouTube, search, queue, playlists, library-first !play
│   ├── library.py            # !save / !library: per-guild uploaded track library
│   ├── intros.py             # Per-user/bot join sounds with schedule support
│   ├── soundboard.py         # Reaction-based soundboard panel + quick trigger
│   ├── tts.py                # edge-tts voice output, per-guild voice setting
│   ├── help.py               # Paginated !help with 8 i18n-driven sections
│   ├── settings.py           # Per-guild feature toggles and language settings
│   ├── listener.py           # Voice receive placeholder (future STT)
│   ├── devlog.py             # !devlog: per-server error forwarding to a channel or DM
│   └── dev.py                # Owner-only: reload, restart, sync, status
│
├── utils/                    # Shared libraries — no Discord command logic here
│   ├── __init__.py
│   ├── config.py             # Loads config.yaml → typed constants and paths
│   ├── guild_state.py        # GuildState dataclass: typed per-guild runtime state
│   ├── guild_config.py       # Per-guild JSON-backed settings (notify_*, locale, TTS voice/rate)
│   ├── persistence.py        # BaseConfig: shared JSON load/save for all config types
│   ├── voice.py              # VoiceStreamer: join, leave, queue, play, interrupt/resume
│   ├── message.py            # MessageWriter: embed builder, error/success/info helpers
│   ├── notifier.py           # Notifier: routes responses to text/TTS/react-only per guild
│   ├── i18n.py               # Locale lookup with per-guild language and keyword interpolation
│   ├── devlog.py             # Dev log: guild-tagged logging handler → Discord channel/DM
│   ├── library.py            # Per-guild track library: slugs, quota, lookup by name/#N
│   ├── intro_config.py       # Per-guild intro assignments and day-schedule overrides
│   ├── soundboard_config.py  # Soundboard metadata: sounds, emoji pool, short triggers
│   ├── reactions.py          # ReactionHandler: yes/no confirm, panel reactions
│   ├── audio.py              # AudioFileManager: validate ext, receive attachment, copy
│   ├── downloader.py         # Downloader class: pluggable sources (YouTube, Suno, ...)
│   ├── cleanup.py            # purge_old_files(): delete stale downloads and logs on startup
│   └── shutdown.py           # Graceful shutdown helpers for PM2-managed restart cycle
│
├── locales/                  # i18n content
│   ├── en.yaml               # English strings
│   ├── sr.yaml               # Serbian strings
│   └── banners/              # Help page content (title + body per page key, per locale)
│       ├── en.yaml
│       └── sr.yaml
│
├── data/                     # All runtime-generated files (gitignored except structure)
│   ├── downloads/            # Cached downloaded audio (yt-dlp output + TTS temp files)
│   ├── intro_sounds/         # Per-user intro audio files
│   ├── soundboard/           # Soundboard audio files
│   ├── library/<guild_id>/   # Uploaded tracks, one folder per guild
│   ├── logs/                 # Rotating log files
│   ├── playlists.json        # Saved playlists (per bot instance)
│   ├── intro_config.json     # Intro assignments and schedules (per guild)
│   ├── soundboard_config.json
│   ├── guild_config.json     # Per-guild settings: notify_*, locale, TTS voice/rate
│   ├── devlog_config.json    # Dev log destinations (per guild + owner DM)
│   └── library_config.json   # Uploaded track metadata (per guild)
│
└── tests/
    ├── conftest.py                # Shared fixtures: mock_bot, ctx, guild_state, voice_client
    ├── test_config.py
    ├── test_guild_state.py
    ├── test_guild_config.py
    ├── test_persistence.py
    ├── test_voice.py
    ├── test_message.py
    ├── test_notifier.py
    ├── test_reactions.py
    ├── test_audio.py
    ├── test_downloader.py
    ├── test_library.py
    ├── test_intro_config.py
    ├── test_soundboard_config.py
    ├── test_cleanup.py
    ├── test_shutdown.py
    ├── test_devlog.py
    ├── test_music_cog.py
    ├── test_library_cog.py
    ├── test_intros_cog.py
    ├── test_soundboard_cog.py
    ├── test_tts_cog.py
    ├── test_help_cog.py
    ├── test_settings_cog.py
    ├── test_devlog_cog.py
    └── test_dev_cog.py        # (not yet written — owner-only commands)
```

---

## Configuration

### `config.yaml` — Locality file

Everything that identifies this bot lives here. Changing bot name, prefix, colors, or emojis requires touching only this file.

```yaml
bot:
  name: Echo
  prefix: "!"
  color: 0x5865F2          # Embed accent color
  emojis:
    yes: "✅"
    no: "❌"
    music: "🎵"
    speaking: "🔊"
    loading: "⏳"

audio:
  panel_timeout: 300       # Seconds before soundboard panel expires
  max_queue: 100

tts:
  default_voice: "en-US-AriaNeural"
  default_rate: "+0%"
```

### `.env` — Secrets only

```
DISCORD_TOKEN=
OWNER_ID=               # For DevCog owner-only commands
```

### `utils/config.py`

Loads `config.yaml` at import time and exposes typed constants:

```python
BOT_NAME: str
PREFIX: str
COLOR: int
EMOJI_YES: str
EMOJI_NO: str
EMOJI_MUSIC: str
EMOJI_SPEAKING: str
PANEL_TIMEOUT: int
MAX_QUEUE: int
TTS_DEFAULT_VOICE: str
TTS_DEFAULT_RATE: str
DATA_DIR: Path
DOWNLOADS_DIR: Path
INTRO_SOUNDS_DIR: Path
SOUNDBOARD_DIR: Path
LOGS_DIR: Path
PLAYLISTS_FILE: Path
INTRO_CONFIG_FILE: Path
SOUNDBOARD_CONFIG_FILE: Path
DEVLOG_CONFIG_FILE: Path
LIBRARY_CONFIG_FILE: Path
LIBRARY_DIR: Path
LIBRARY_MAX_TRACKS: int
LIBRARY_MAX_TOTAL_MB: int
LIBRARY_CONFIRM_SECS: int
```

All paths are derived from `DATA_DIR` which is `echo-bot/data/`. Directories are created on import if missing.

---

## Core Utils

### `utils/guild_state.py` — GuildState

Typed dataclass for per-guild runtime state.

```python
@dataclass
class GuildState:
    queue: deque[Track] = field(default_factory=deque)
    voice_client: discord.VoiceClient | None = None
    current_track: Track | None = None
    interrupted_track: Track | None = None   # paused track during interrupt
    tts_queue: deque[str] = field(default_factory=deque)
    tts_voice: str = TTS_DEFAULT_VOICE
    soundboard_panel_message: discord.Message | None = None

@dataclass
class Track:
    title: str
    url: str                 # source URL or local file path
    file_path: Path | None   # local cached path if downloaded
    duration: int | None     # seconds
    requester: discord.Member | None
```

`bot.get_guild_state(guild_id: int) -> GuildState` creates on first access.

### `utils/guild_config.py`

Per-guild JSON-backed settings. Module functions (not a class). Used by `SettingsCog`, `TTSCog`, `IntrosCog`, and `Notifier`.

Stored fields per guild: `auto_join`, `auto_leave`, `notify_write`, `notify_say`, `notify_song_text`, `notify_song_voice`, `notify_say_text`, `notify_say_voice`, `locale`, `voice_language`, `tts_voice`, `tts_rate`. Defaults come from `config.yaml` and are not stored unless overridden. Writes via `BaseConfig` (atomic).

### `utils/persistence.py` — BaseConfig

All JSON-backed config types inherit from this.

```python
class BaseConfig:
    path: Path                           # subclass sets this as class var
    def load(self) -> dict
    def save(self, data: dict) -> None
    def get(self, key: str, default=None)
    def set(self, key: str, value) -> None
```

Subclasses (`IntroConfig`, `SoundboardConfig`, `PlaylistConfig`) define schema-specific query methods on top.

### `utils/voice.py` — VoiceStreamer

Single class per guild managing all voice interactions. Cogs never touch `VoiceClient` directly.

```python
class VoiceStreamer:
    async def join(self, channel: discord.VoiceChannel) -> None
    async def leave(self) -> None
    async def play(self, track: Track) -> None         # enqueue + start if idle
    async def play_next(self) -> None                  # internal: advance queue
    async def interrupt(self, track: Track) -> None    # pause current, play track, resume
    async def skip(self) -> Track | None               # returns skipped track
    async def stop(self) -> None                       # clear queue, stop playback
    async def pause(self) -> None
    async def resume(self) -> None
    async def replay(self) -> Track | None             # restart current track
    @property
    def is_playing(self) -> bool
    @property
    def queue(self) -> deque[Track]
```

Auto-leave when the last non-bot member leaves the voice channel is handled inside `VoiceStreamer` via `on_voice_state_update`, not in cogs.

### `utils/message.py` — MessageWriter

Centralized embed construction. All cogs use this — no inline `discord.Embed()` calls.

```python
class MessageWriter:
    @staticmethod
    def success(title: str, description: str = "") -> discord.Embed
    @staticmethod
    def error(title: str, description: str = "") -> discord.Embed
    @staticmethod
    def info(title: str, description: str = "") -> discord.Embed
    @staticmethod
    def track_card(track: Track, guild_id: int) -> discord.Embed
    @staticmethod
    def queue_page(tracks: list[Track], page: int, total_pages: int, guild_id: int) -> discord.Embed
    @staticmethod
    def soundboard_panel(sounds: dict, guild_id: int) -> discord.Embed
    @staticmethod
    def devlog(records: list[logging.LogRecord]) -> discord.Embed
```

Color is injected from `config.COLOR`. Bot name appears in embed footers automatically.

### `utils/notifier.py` — Notifier

Response delivery router. Reads per-guild `notify_write` and `notify_say` settings and routes command responses to:
- **Write only** (default): sends a text embed
- **Say only**: reacts with ✅/❌/❓ and speaks via TTS
- **Both**: sends embed and speaks
- **Neither**: reacts only

All cogs use `Notifier` instead of calling `ctx.send()` directly. `Notifier.success()`, `.error()`, `.loading()`, and `.track_card()` cover the standard response patterns.

### `utils/i18n.py`

Locale lookup with per-guild language resolution and keyword interpolation.

```python
def t(key: str, guild_id: int = 0, **kwargs) -> str
```

Reads YAML locale files from `locales/` and `locales/banners/`. Per-guild locale is resolved from `GuildConfig`. Falls back to `en`. Supported locales: `en`, `sr`.

### `utils/reactions.py` — ReactionHandler

```python
class ReactionHandler:
    @staticmethod
    async def confirm(ctx, prompt: str, timeout: float = 30.0) -> bool
    # Sends prompt, waits for ✅/❌ from ctx.author, returns True/False

    @staticmethod
    async def panel(ctx, options: dict[str, callable], embed: discord.Embed, timeout: float = PANEL_TIMEOUT) -> None
    # Sends embed, adds emoji reactions from options keys,
    # dispatches to callable on each reaction, cleans up on timeout
```

### `utils/audio.py` — AudioFileManager

```python
AUDIO_EXTS = {".mp3", ".ogg", ".wav", ".flac", ".m4a", ".opus", ".aac"}

class AudioFileManager:
    @staticmethod
    async def receive_attachment(ctx, dest_dir: Path, filename: str) -> Path | None
    # Validates extension, downloads attachment, saves to dest_dir/filename
    # Returns path on success, sends error embed and returns None on failure

    @staticmethod
    def is_valid_audio(filename: str) -> bool
```

### `utils/downloader.py` — Downloader

Pluggable source architecture for audio acquisition. New sources are added without touching cog code.

```python
class Downloader:
    @staticmethod
    async def resolve(query: str) -> Track
    # Routes to correct source based on URL pattern or falls back to YouTube search

    @staticmethod
    async def download(track: Track) -> Path
    # Downloads to DOWNLOADS_DIR, returns local path; uses cache if already present
```

Source handlers (internal):
- `_youtube(query)` — yt-dlp
- `_resolve_suno(url)` / `_download_suno(track)` — Suno via its clip API (yt-dlp refuses suno.com since 2026.08): metadata + `video_url` MP4 (AAC audio, played with `-vn`). **Marked Withdrawn** — Suno API broke in Nov 2026; handler remains in code but is unreachable via normal `!play`.
- Future: `_spotify_preview(url)`, `_soundcloud(url)`

### `utils/cleanup.py`

`purge_old_files()` — deletes files older than 7 days from `data/logs/` and `data/downloads/`. Called by `bot.py` on startup.

### `utils/shutdown.py`

Graceful shutdown helpers used by the PM2-managed restart cycle (`!restart` → `sys.exit(0)` → PM2 auto-restart).

---

## Cogs

### `cogs/music.py` — MusicCog

Hybrid commands (prefix + slash). All audio routing via `VoiceStreamer`. All output via `Notifier` + `MessageWriter`. Checks the guild's uploaded library before searching online.

| Command | Aliases | Description |
|---|---|---|
| `!play <query>` | `!p` | Play or enqueue; YouTube URL or search term. Checks library first; shows a "switch to YouTube?" prompt for name matches. |
| `!skip` | `!s` | Skip current track |
| `!pause` | — | Pause playback |
| `!resume` | `!unpause` | Resume playback |
| `!stop` | — | Stop and clear queue |
| `!replay` | `!rp` | Restart the current track from the beginning |
| `!nowplaying` | `!np` | Show the currently playing track card |
| `!queue [page]` | `!q` | Show queue (10 per page) |
| `!clear` | — | Clear queue without stopping current track |
| `!remove <pos>` | `!rm` | Remove a track by queue position number |
| `!shuffle` | — | Shuffle the queue |
| `!join` | — | Join caller's voice channel |
| `!leave` | `!disconnect`, `!dc` | Leave voice channel and clear all state |
| `!playlist` | `!pl` | Playlist group — bare invocation shows subcommand hint |
| `!playlist save <name>` | — | Save current queue + playing track as a named playlist |
| `!playlist load <name>` | — | Load a playlist into the queue |
| `!playlist list` | — | List all saved playlists with track counts |
| `!playlist delete <name>` | — | Delete a playlist |
| `!playlist show <name>` | — | Show contents of a playlist (up to 20 tracks) |

### `cogs/intros.py` — IntrosCog

Trigger types: `bot` (bot join), `user` (any user join), `user_<id>` (specific member).

| Command | Description |
|---|---|
| `!intro set <trigger>` | Set default intro (attachment or URL). Trigger: bot/user/@mention |
| `!intro schedule <trigger> <days>` | Day-specific override (MON-FRI, WEEKDAY, SAT,SUN, etc.) |
| `!intro unschedule <trigger> <days>` | Remove a day-specific override |
| `!intro clear <trigger>` | Remove all intros for a trigger (deletes audio files) |
| `!intro rename <trigger> <name>` | Update source label of a trigger's default entry |
| `!intro list` | List all triggers configured for this server |
| `!intro show` | Show bot/user overview and global enable flags |
| `!intro trigger <trigger>` | Manually play an intro |
| `!intro autojoin on\|off` | Toggle bot auto-join (updates guild_config `auto_join`) |

Plays via `VoiceStreamer.interrupt()` — pauses music and resumes after.
Bot-join intro fires via `on_voice_state_update` when `member.id == bot.user.id`.

### `cogs/soundboard.py` — SoundboardCog

| Command | Aliases | Description |
|---|---|---|
| `!sb add <name> [💥] [\| short]` | `!soundboard add` | Add sound (attachment). Name may contain spaces; emoji and short optional. |
| `!sb remove <name>` | `!soundboard remove` | Remove sound |
| `!sb play <name>` | `!soundboard play` | Play sound immediately |
| `!sb short <name> <short>` | `!soundboard short` | Change short trigger for a sound |
| `!sb list` | `!soundboard list` | Show all sounds |
| `!sb panel` | `!soundboard panel` | Post persistent reaction panel |

Plays via `VoiceStreamer.interrupt()`.

**`sb add` parsing:** `_parse_add_text(text)` splits an optional short trigger at `|`, lifts the first emoji found anywhere out of the remainder, and treats the rest as the name (spaces allowed). Omitted short defaults to `name.replace(' ', '').lower()`; omitted emoji is filled from `soundboard_config.EMOJI_POOL` via `next_free_emoji()`, falling back to `DEFAULT_EMOJI` once the pool is exhausted.

**Quick trigger:** `on_message` tries the whole text after the prefix against names and shorts first, then the first word, so `!epic fail sound` works as well as `!ef`. Registered commands always take priority.

**`sb short` parsing:** `rsplit(maxsplit=1)` — last word is the new short, the rest is the sound name. No quotes needed for multi-word names.

Schema: `{"explosion effect": {"emoji": "💥", "file": "explosion effect.mp3", "short": "ex"}}` — `short` is always present (auto-generated if not supplied).

### `cogs/tts.py` — TTSCog

Uses [edge-tts](https://github.com/rany2/edge-tts) to synthesize speech and play it in voice. Per-guild voice and rate settings stored in `GuildConfig`. Audio synthesized to a temp file in `data/downloads/`, played via interrupt, then deleted.

| Command | Description |
|---|---|
| `!say <text>` | Speak text in caller's voice channel |
| `!tts voice <name>` | Set TTS voice for this guild |
| `!tts voices [locale]` | List available edge-tts voices, optionally filtered by locale prefix (e.g. `en`, `sr`) |
| `!tts rate <value>` | Set speech rate (e.g. `+10%`, `-20%`) |
| `!tts stop` | Clear TTS queue |
| `!tts show` | Show current TTS voice and rate for this server |

### `cogs/library.py` — LibraryCog

Per-guild library of uploaded tracks — the dependable alternative to third-party sources.

| Command | Aliases | Description |
|---|---|---|
| `!save [name]` | `!upload` | Store the attached (or replied-to) audio file; name defaults to the filename |
| `!library [query]` | `!lib` | Numbered list + dropdown picker + page buttons. With a name or `#N`, plays immediately. |
| `!lib play <query>` | — | Play an uploaded track by name or `#N` |
| `!lib remove <query>` | `!lib delete` | Remove a track by name or `#N` |
| `!lib rename <query> <new name>` | — | Rename a track |
| `!lib info <query>` | — | Show details: duration, size, who added it, play count |

`!play <name>` consults the library first (`MusicCog._try_library`): a `#N` reference plays at once, while a name match shows `_LibrarySwitchView` for `LIBRARY_CONFIRM_SECS` seconds offering a YouTube search instead. The countdown is `asyncio.wait_for(view.wait(), ...)` rather than discord's view timer, so it does not depend on the view being registered with the client.

### `utils/library.py` — track library

- Files: `LIBRARY_DIR/<guild_id>/<slug>.<ext>`; metadata in `library_config.json` keyed by guild.
- `slugify` gives the filesystem/command-safe key; `track_list` sorts by title and defines the `#N` numbering, so no per-channel selection state is stored.
- `find`/`find_all` match exact slug or title first, then partial titles; `resolve` also accepts `#N`.
- `check_quota` enforces `LIBRARY_MAX_TRACKS` and `LIBRARY_MAX_TOTAL_MB` per guild; `probe_duration` shells out to ffprobe and degrades to `None` when unavailable.
- No Discord types — cogs own all presentation.

### `cogs/help.py` — HelpCog

Paginated help driven by the i18n locale system. 8 pages: `overview`, `music`, `library`, `queue`, `intros`, `soundboard`, `tts`, `settings`. Content changes with the guild's locale (`GuildConfig.locale`).

| Command | Aliases | Description |
|---|---|---|
| `!help [section]` | `!h` | Show paginated help with Prev/Next buttons. Optional section jump by name. |

The `test_help_cog.py` test suite **enforces** that every visible command is named in the `!help` pages, in `help.md`, and in `FEATURES.md`. It also checks that no stale `!command` appears in any of the three surfaces.

### `cogs/settings.py` — SettingsCog

Per-guild feature flags. Requires **Manage Server** permission. Settings persist in `guild_config.json` via `guild_config.py` module functions.

| Command | Aliases | Description |
|---|---|---|
| `!settings` | `!config` | Show all current settings for this server |
| `!settings show` | — | Same as bare `!settings` |
| `!settings set <key> <true\|false>` | — | Override a boolean setting for this server |
| `!settings reset <key>` | — | Revert a setting to the global default |
| `!settings locale [code]` | `!settings language` | Set or show the display language (`en`, `sr`) |
| `!settings voice_language [code]` | — | Set the TTS voice language prefix; empty = use full `tts_voice` |

Toggle keys: `auto_join`, `auto_leave`, `notify_write`, `notify_say`, `notify_song_text`, `notify_song_voice`, `notify_say_text`, `notify_say_voice`.

### `cogs/listener.py` — ListenerCog (stub)

Placeholder cog. `GuildState` already reserves space for recording state. The cog loads, registers a `!listen` command that responds "voice listening not yet implemented", and documents the expected integration point for a future STT library (e.g. faster-whisper).

### `cogs/dev.py` — DevCog

Owner-only (checked via `bot.owner_id` from `OWNER_ID` env var). Prefix commands only — never slash commands, to avoid accidental exposure. `!version` is the one public exception.

| Command | Access | Description |
|---|---|---|
| `!reload <cog>` | Owner | Hot-reload a cog + its utils dependencies |
| `!restart` | Owner | Graceful shutdown (PM2 auto-restarts) |
| `!sync [guild_id]` | Owner | Sync slash command tree (global or guild-scoped) |
| `!status` | Owner | Show queue state, voice connections, uptime |
| `!cogs` | Owner | List loaded cogs and their status |
| `!version` | Everyone | Show the running bot version from `config.yaml` |

### `cogs/devlog.py` — DevlogCog

`!devlog [here|dm|off|test] [all]` — prefix only. Turns on per-server error forwarding. Requires **Manage Server** (or bot owner); `all` and DM use are owner-only. In a DM with the bot, `!devlog here` subscribes the owner to every record from every server (`owner_dm`).

### `utils/devlog.py` — Dev log

- `current_guild` ContextVar — set in `bot.py` (`on_message`, `on_voice_state_update`, `before_invoke`) and in `VoiceStreamer.play_next` / `interrupt`. Code on FFmpeg player threads passes `extra={'guild_id': ...}` instead.
- `GuildContextFilter` stamps `record.guild_id`; `targets_for(guild_id)` routes: a guild's records → that guild's target; unscoped records → targets with `all`; `owner_dm` → everything.
- `DevlogHandler` (module-level `handler`, attached to the root logger in `bot.py`, started in `on_ready`): WARNING+, thread-safe `emit`, batches for `BATCH_WINDOW` (3 s), max `MAX_ENTRIES` (5) per message per target, rendered with `MessageWriter.devlog`. Records logged before start are kept (up to 200). Its own send failures are never forwarded.
- `utils.devlog` is intentionally **not** in DevCog's hot-reload list — reloading it would split the ContextVar between old and new module objects.

FFmpeg errors: `_make_source` sends FFmpeg's stderr to a temp file with `-loglevel error`; the after-callbacks call `_report_ffmpeg_errors`, which logs any output as a WARNING. This surfaces failures that otherwise end playback silently.

---

## Hot Reload Strategy

Three layers:

| Layer | Mechanism | Covers |
|---|---|---|
| `!reload <cog>` | `bot.reload_extension()` + `importlib.reload()` on utils the cog imports | Cog logic, commands, responses — 95% of day-to-day changes |
| `!restart` | `sys.exit(0)` → PM2 auto-restarts process | bot.py changes, dependency updates |
| PM2 watchdog | `autorestart: true`, `max_restarts: 10`, `restart_delay: 3000` | Crashes, uncaught exceptions |

`!reload` implementation:
1. `importlib.reload()` each utils module the cog depends on
2. `await bot.reload_extension(f"cogs.{cog_name}")`
3. Report success/failure in embed

Slash command tree must be re-synced after reloading cogs that add or remove slash commands (`!sync` after `!reload`).

---

## Entry Point (`bot.py`)

- Loads `config.yaml` and `.env` before anything else
- Calls `purge_old_files()` to delete stale files from `data/logs/` and `data/downloads/`
- Sets up per-run rotating file loggers (`data/logs/echo_<timestamp>.log` and `errors_<timestamp>.log`, 5 MB / 2 MB max, 3/5 backups) — no console handler; all output goes to files
- Creates `commands.Bot` with `command_prefix=PREFIX`, `intents`, `help_command=None`
- Attaches `get_guild_state(guild_id) -> GuildState` helper to bot instance
- Loads all cogs in order: `music`, `library`, `intros`, `soundboard`, `tts`, `help`, `settings`, `listener`, `devlog`, `dev`
- Adds `devlog.handler` to the root logger; tags each event/command with its guild for it
- On `on_ready`: starts the dev log sender, logs bot name/ID, syncs slash tree to dev guild if `DEV_GUILD_ID` is set
- On `on_command_error`: routes to `MessageWriter.error()` for unknown commands, missing args, permission errors

---

## PM2 (`pm2.config.js`)

```js
module.exports = {
  apps: [{
    name: 'echo-bot',
    script: 'bot.py',
    interpreter: 'python',
    cwd: '/path/to/echo-bot',
    watch: false,
    autorestart: true,
    max_restarts: 10,
    restart_delay: 3000,
    env: { PYTHONUNBUFFERED: '1' }
  }]
}
```

`watch: false` — reloading is handled by `!reload`/`!restart` commands, not file watching.

---

## Testing

**Framework:** pytest + pytest-asyncio + pytest-mock  
**Run:** `pytest` from `echo-bot/`  
**Config:** `pytest.ini` with `asyncio_mode = auto`

### Fixtures (`tests/conftest.py`)

```python
mock_bot          # AsyncMock bot with get_guild_state()
guild_id          # int: 123456789
guild_state       # GuildState() default instance
voice_client      # MagicMock discord.VoiceClient
ctx               # MagicMock context with author in voice channel
ctx_no_voice      # MagicMock context with author not in voice
sample_track      # Track(title="Test", url="...", ...)
```

### Rules

- Every new command → test in the relevant cog test file
- Every new util function → test in the relevant util test file
- Mocks go in conftest, not duplicated per-file
- Run `pytest` from `echo-bot/` before every commit and verify it passes
- `test_help_cog.py` enforces that `help.md`, `FEATURES.md`, and the `!help` i18n pages all stay in sync with the real command set

---

## Rules for Working on echo-bot

- Help: update `echo-bot/help.md` whenever commands are added, removed, or renamed (enforced by tests)
- Features: update `echo-bot/FEATURES.md` on the same change (enforced by tests)
- Tests: every change needs a corresponding test in `echo-bot/tests/`
- Architecture: update this file when structure changes
- Paths: always derive paths from `utils/config.py` constants — never hardcode `data/` paths in cogs
- Embeds: always use `MessageWriter` — never build `discord.Embed` inline in cogs
- Voice: always use `VoiceStreamer` — never call `VoiceClient` methods directly in cogs
- Persistence: always use the config modules (`guild_config`, `IntroConfig`, etc.) — never write JSON directly from a cog
