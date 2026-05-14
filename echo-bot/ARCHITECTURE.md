# Echo Bot — Architecture

> **Session start rule:** Read this file at the beginning of every session before touching any code.

## Overview

Echo is a Discord bot for server audio interaction: music playback, soundboard, per-user intro sounds, and TTS voice output (with voice listening as a future capability). It lives at `echo-bot/` inside the `DiscordBots` monorepo alongside the legacy `music-bot/` (which is frozen and not modified).

Echo supports both `!` prefix commands and `/` slash commands via discord.py hybrid commands. A single command definition covers both surfaces.

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
│   ├── music.py              # Playback: YouTube, Suno, search, queue, playlists
│   ├── intros.py             # Per-user/bot join sounds with schedule support
│   ├── soundboard.py         # Reaction-based soundboard panel
│   ├── tts.py                # edge-tts voice output, per-guild voice setting
│   ├── listener.py           # Voice receive placeholder (future STT)
│   └── dev.py                # Owner-only: reload, restart, sync, status
│
├── utils/                    # Shared libraries — no Discord command logic here
│   ├── __init__.py
│   ├── config.py             # Loads config.yaml → typed constants
│   ├── guild_state.py        # GuildState dataclass: typed per-guild runtime state
│   ├── persistence.py        # BaseConfig: shared JSON load/save for all config types
│   ├── voice.py              # VoiceStreamer: join, leave, queue, play, interrupt/resume
│   ├── message.py            # MessageWriter: embed builder, error/success/info helpers
│   ├── reactions.py          # ReactionHandler: yes/no confirm, panel reactions
│   ├── audio.py              # AudioFileManager: validate ext, receive attachment, copy
│   └── downloader.py         # Downloader class: pluggable sources (YouTube, Suno, ...)
│
├── data/                     # All runtime-generated files (gitignored except structure)
│   ├── downloads/            # Cached downloaded audio (yt-dlp output)
│   ├── intro_sounds/         # Per-user intro audio files
│   ├── soundboard/           # Soundboard audio files
│   ├── logs/                 # Rotating log files
│   ├── playlists.json        # Saved playlists (per guild)
│   ├── intro_config.json     # Intro assignments and schedules (per guild)
│   └── soundboard_config.json
│
└── tests/
    ├── conftest.py           # Shared fixtures: mock_bot, ctx, guild_state, voice_client
    ├── test_config.py
    ├── test_guild_state.py
    ├── test_persistence.py
    ├── test_voice.py
    ├── test_message.py
    ├── test_reactions.py
    ├── test_audio.py
    ├── test_downloader.py
    ├── test_music_cog.py
    ├── test_intros_cog.py
    ├── test_soundboard_cog.py
    ├── test_tts_cog.py
    └── test_dev_cog.py
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
```

All paths are derived from `DATA_DIR` which is `echo-bot/data/`. Directories are created on import if missing.

---

## Core Utils

### `utils/guild_state.py` — GuildState

Typed dataclass replacing the raw `bot.guild_states[id]` dicts from music-bot.

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

### `utils/persistence.py` — BaseConfig

All JSON-backed config types inherit from this. Eliminates the load/save duplication between `intro_config.py` and `soundboard_config.py`.

```python
class BaseConfig:
    path: Path                           # subclass sets this as class var
    def load(self) -> dict
    def save(self, data: dict) -> None
    def get(self, key: str, default=None)
    def set(self, key: str, value) -> None
```

Subclasses (`IntroConfig`, `SoundboardConfig`, `PlaylistConfig`) only define schema-specific query methods.

### `utils/voice.py` — VoiceStreamer

Single class per guild managing all voice interactions. Cogs never touch `VoiceClient` directly.

```python
class VoiceStreamer:
    async def join(self, channel: discord.VoiceChannel) -> None
    async def leave(self) -> None
    async def play(self, track: Track) -> None         # enqueue + start if idle
    async def play_next(self) -> None                  # internal: advance queue
    async def interrupt(self, track: Track) -> None    # pause current, play track, resume
    async def skip(self) -> None
    async def stop(self) -> None                       # clear queue, stop playback
    async def pause(self) -> None
    async def resume(self) -> None
    @property
    def is_playing(self) -> bool
    @property
    def queue(self) -> deque[Track]
```

Auto-leave when the last non-bot member leaves the voice channel is handled inside `VoiceStreamer` via the `on_voice_state_update` event, not in cogs.

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
    def track_card(track: Track) -> discord.Embed
    @staticmethod
    def queue_page(tracks: list[Track], page: int, total_pages: int) -> discord.Embed
    @staticmethod
    def soundboard_panel(sounds: list[str]) -> discord.Embed
```

Color is injected from `config.COLOR`. Bot name appears in embed footers automatically.

### `utils/reactions.py` — ReactionHandler

Extracted from the `_ask_to_join` duplication (40+ lines copied between intros and soundboard in music-bot).

```python
class ReactionHandler:
    @staticmethod
    async def confirm(
        ctx,
        prompt: str,
        timeout: float = 30.0
    ) -> bool
    # Sends prompt, waits for ✅/❌ from ctx.author, returns True/False

    @staticmethod
    async def panel(
        ctx,
        options: dict[str, callable],
        embed: discord.Embed,
        timeout: float = PANEL_TIMEOUT
    ) -> None
    # Sends embed, adds emoji reactions from options keys,
    # dispatches to callable on each reaction, cleans up on timeout
```

### `utils/audio.py` — AudioFileManager

Consolidates the download → validate → copy pattern repeated across intros and soundboard cogs.

```python
AUDIO_EXTS = {".mp3", ".ogg", ".wav", ".flac", ".m4a", ".opus", ".aac"}

class AudioFileManager:
    @staticmethod
    async def receive_attachment(
        ctx,
        dest_dir: Path,
        filename: str
    ) -> Path | None
    # Validates extension, downloads attachment, saves to dest_dir/filename
    # Returns path on success, sends error embed and returns None on failure

    @staticmethod
    def is_valid_audio(filename: str) -> bool
    # Checks extension against AUDIO_EXTS
```

### `utils/downloader.py` — Downloader

Pluggable source architecture for audio acquisition. New sources (Spotify previews, etc.) are added without touching cog code.

```python
class Track:  # defined in guild_state.py, imported here
    ...

class Downloader:
    @staticmethod
    async def resolve(query: str) -> Track
    # Routes to correct source based on URL pattern or falls back to YouTube search

    @staticmethod
    async def download(track: Track) -> Path
    # Downloads to DOWNLOADS_DIR, returns local path; uses cache if already present
```

Source handlers (internal, not exposed to cogs):
- `_youtube(query)` — yt-dlp
- `_suno(url)` — Suno direct download
- Future: `_spotify_preview(url)`, `_soundcloud(url)`

---

## Cogs

### `cogs/music.py` — MusicCog

Hybrid commands (prefix + slash). All audio routing via `VoiceStreamer`. All output via `MessageWriter`.

| Command | Aliases | Description |
|---|---|---|
| `!play <query>` | `!p` | Play or enqueue; YouTube URL, Suno URL, or search |
| `!skip` | `!s` | Skip current track |
| `!pause` | — | Pause playback |
| `!resume` | — | Resume playback |
| `!stop` | — | Stop and clear queue |
| `!queue` | `!q` | Show queue (paginated) |
| `!join` | `!j` | Join caller's voice channel |
| `!leave` | `!dc` | Leave voice channel |
| `!clear` | — | Clear queue without stopping |
| `!cleanup` | — | Delete bot messages in channel |
| `!playlist <sub>` | `!pl` | save / load / list / show / add / remove / delete |
| `!help` | `!h` | Paginated help (Prev/Next buttons) |

### `cogs/intros.py` — IntrosCog

| Command | Aliases | Description |
|---|---|---|
| `!intro set <user>` | `!in set` | Assign an intro sound to a user (attachment) |
| `!intro schedule <user> <days> <time>` | — | Day/time-scoped intro overrides |
| `!intro unschedule <user>` | — | Remove schedule |
| `!intro clear <user>` | — | Remove intro for user |
| `!intro list` | — | List all assigned intros |
| `!intro show <user>` | — | Show intro details for user |
| `!intro rename <user> <name>` | — | Rename intro file |
| `!intro trigger <user>` | — | Manually fire an intro |
| `!intro autojoin` | — | Toggle auto-join behavior |

Plays via `VoiceStreamer.interrupt()` — does not kill music, pauses and resumes.

### `cogs/soundboard.py` — SoundboardCog

| Command | Aliases | Description |
|---|---|---|
| `!soundboard add <name>` | `!sb add` | Add sound (attachment) |
| `!soundboard remove <name>` | `!sb remove` | Remove sound |
| `!soundboard trigger <name>` | `!sb trigger` | Play sound immediately |
| `!soundboard list` | `!sb list` | Show all sounds |
| `!soundboard panel` | `!sb panel` | Open interactive reaction panel |

Panel uses `ReactionHandler.panel()`. Plays via `VoiceStreamer.interrupt()`.

### `cogs/tts.py` — TTSCog

Uses [edge-tts](https://github.com/rany2/edge-tts) to synthesize speech and play it in voice.

| Command | Description |
|---|---|
| `!say <text>` | Speak text in caller's voice channel |
| `!tts voice <name>` | Set TTS voice for this guild |
| `!tts voices` | List available edge-tts voices |
| `!tts rate <value>` | Set speech rate (e.g. `+10%`, `-20%`) |
| `!tts stop` | Clear TTS queue |

TTS audio is generated to a temp file in `data/downloads/`, played via `VoiceStreamer.interrupt()`, then deleted.

### `cogs/listener.py` — ListenerCog (stub)

Placeholder cog. `GuildState` already reserves space for recording state. The cog loads, registers a `!listen` command that responds "voice listening not yet implemented", and documents the expected integration point for a future STT library (e.g. faster-whisper).

### `cogs/dev.py` — DevCog

Owner-only (checked via `bot.owner_id` from `OWNER_ID` env var). Prefix commands only — never slash commands, to avoid accidental exposure.

| Command | Description |
|---|---|
| `!reload <cog>` | Hot-reload a cog + its utils dependencies |
| `!restart` | Graceful shutdown (PM2 auto-restarts) |
| `!sync [guild_id]` | Sync slash command tree (global or guild-scoped) |
| `!status` | Show queue state, voice connections, uptime |
| `!cogs` | List loaded cogs and their status |

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
- Sets up rotating file logger (`data/logs/echo.log`, 5 MB max, 3 backups) + console handler
- Creates `commands.Bot` with `command_prefix=PREFIX`, `intents`, `help_command=None`
- Attaches `get_guild_state(guild_id) -> GuildState` helper to bot instance
- Loads all cogs in order: `music`, `intros`, `soundboard`, `tts`, `listener`, `dev`
- On `on_ready`: logs bot name/ID, syncs slash tree to dev guild if `DEV_GUILD_ID` is set
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

---

## Build Phases

| Phase | What | Status |
|---|---|---|
| 1 | Scaffold: folder structure, `config.yaml`, `bot.py`, `pm2.config.js`, `utils/config.py` | Planned |
| 2 | Core utils: `guild_state`, `persistence`, `message`, `reactions`, `voice`, `audio`, `downloader` + tests | Planned |
| 3 | Port cogs: `music`, `intros`, `soundboard` rewritten using new utils + tests | Planned |
| 4 | New cogs: `tts` (edge-tts), `dev` (reload/restart/sync), `listener` (stub) + tests | Planned |
| 5 | Polish: `help.md`, slash command sync, PM2 setup docs, ARCHITECTURE.md updates | Planned |

---

## Rules for Working on echo-bot

- **music-bot is frozen** — do not modify anything in `music-bot/`
- Help: update `echo-bot/help.md` whenever commands are added, removed, or renamed
- Tests: every change needs a corresponding test in `echo-bot/tests/`
- Architecture: update this file when structure changes
- Paths: always derive paths from `utils/config.py` constants — never hardcode `data/` paths in cogs
- Embeds: always use `MessageWriter` — never build `discord.Embed` inline in cogs
- Voice: always use `VoiceStreamer` — never call `VoiceClient` methods directly in cogs
