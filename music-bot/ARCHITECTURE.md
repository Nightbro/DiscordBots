# Music Bot — Architecture

## Overview
A Discord music bot built with **discord.py v2** and **yt-dlp**. Audio is downloaded to local MP3 files and streamed via FFmpeg. State is kept in memory per guild; playlists and intro config are persisted to JSON files.

## Entry point
`bot.py` — applies the SSL monkey-patch, configures logging, creates the bot instance, loads cogs, and runs the event loop. It contains no commands — only lifecycle events (`on_ready`, `on_command_error`, `on_message`).

```
bot.py
└── loads cogs/music.py   (MusicCog)
└── loads cogs/intros.py  (IntrosCog)
```

## File structure
```
music-bot/
├── bot.py                   Entry point
├── help.md                  Command reference (keep in sync with _HELP_TEXT)
├── ARCHITECTURE.md          This file
├── requirements.txt         Runtime + dev dependencies
├── pytest.ini               Pytest configuration
│
├── cogs/                    Discord.py Cog extensions
│   ├── music.py             MusicCog — playback, playlists, !help, !join
│   └── intros.py            IntrosCog — !intro commands, on_voice_state_update
│
├── utils/                   Shared, Discord-agnostic modules
│   ├── config.py            Path constants + .env loading (load_dotenv runs here)
│   ├── downloader.py        yt-dlp + Suno CDN download logic, tag helpers
│   ├── player.py            Guild state (get_state) + play_next loop
│   └── intro_config.py      Intro config JSON persistence
│
├── tests/                   pytest test suite
│   ├── conftest.py          Shared fixtures (mock bot, ctx, voice client)
│   ├── test_downloader.py   Unit tests for utils/downloader.py
│   ├── test_player.py       Unit tests for utils/player.py
│   ├── test_intro_config.py Unit tests for utils/intro_config.py
│   ├── test_music_cog.py    Command tests for MusicCog
│   └── test_intros_cog.py   Command tests for IntrosCog
│
├── downloads/               Cached MP3s (git-ignored)
├── intro_sounds/            Per-guild intro MP3s (git-ignored)
├── logs/                    Rotating log files (git-ignored)
├── playlists.json           Saved playlists (per-guild)
└── intro_config.json        Configured intro sounds (per-guild, git-ignored)
```

## Module responsibilities

### `utils/config.py`
Calls `load_dotenv()` and defines all `Path` constants. **Imported first** by `bot.py` so env vars are available everywhere. Also creates required directories on startup.

Key exports: `BASE_DIR`, `DOWNLOADS_DIR`, `LOGS_DIR`, `INTRO_SOUNDS_DIR`, `PLAYLISTS_FILE`, `INTRO_CONFIG_FILE`, `_COOKIES_FILE`, `_INTRO_FILE`, `_INTRO_ON_BOT_JOIN`, `_INTRO_ON_USER_JOIN`

### `utils/downloader.py`
All download logic. Handles YouTube (via yt-dlp) and Suno (via CDN URL). Downloads are cached by video/song ID so repeat plays are instant. Exposes `download_track(query)` as the single entry point.

Key exports: `download_track`, `is_suno_url`, `duration_tag`, `FFMPEG_OPTIONS`, `YDL_INFO`

### `utils/player.py`
Manages per-guild runtime state and the play loop. `get_state(bot, guild_id)` returns (or creates) the `{'queue': deque, 'voice_client': VoiceClient}` dict stored on `bot.guild_states`. `play_next` pops the front of the queue, downloads lazy playlist tracks on demand, and schedules itself via `run_coroutine_threadsafe` when a track ends.

Key exports: `get_state`, `play_next`

### `utils/intro_config.py`
Reads/writes `intro_config.json`. `get_intro_file(guild_id, trigger)` returns the configured intro Path for that guild, falling back to the global `_INTRO_FILE` from `.env`.

Key exports: `load_intro_config`, `save_intro_config`, `get_intro_file`

### `cogs/music.py` — `MusicCog`
All playback commands and playlist management. `_ensure_voice` handles connecting/moving and sets `just_connected` so the bot-join intro can be prepended to the queue.

Commands: `!join`, `!play`, `!skip`, `!pause`, `!resume`, `!stop`, `!queue`, `!clear`, `!leave`, `!cleanup`, `!playlist` (group), `!help`

### `cogs/intros.py` — `IntrosCog`
Per-guild intro sound configuration and the `on_voice_state_update` listener that plays the user-join intro when a user enters the bot's channel while it is idle.

Commands: `!intro set`, `!intro clear`, `!intro show`

## Data flow — playing a song

```
User: !play never gonna give you up
  │
  ├─ ensure_voice()         connect to channel, set just_connected=True
  ├─ download_track(query)  yt-dlp search → download → MP3 in downloads/
  ├─ get_state()            retrieve guild queue
  ├─ [if just_connected]    prepend intro track to queue
  ├─ queue.append(track)
  └─ play_next()
       ├─ queue.popleft()
       ├─ FFmpegPCMAudio(track.file)
       ├─ vc.play(source, after=λ → play_next)
       └─ send "Now playing: ..."
```

## Data flow — intro sounds

```
User joins voice channel
  │
  on_voice_state_update (IntrosCog)
    ├─ guard: not a bot, _INTRO_ON_USER_JOIN=true, joined (not moved/left)
    ├─ bot must be in same channel and idle
    ├─ get_intro_file(guild_id, 'user')
    │     ├─ check intro_config.json for guild-specific file
    │     └─ fallback to _INTRO_FILE (.env INTRO_MP3)
    └─ vc.play(FFmpegPCMAudio(intro))
```

## Persistence
| File | Contents | Git |
|---|---|---|
| `playlists.json` | Per-guild saved playlists | ✅ committed |
| `intro_config.json` | Per-guild intro sound paths + sources | ❌ git-ignored |
| `downloads/*.mp3` | Cached audio | ❌ git-ignored |
| `intro_sounds/*.mp3` | Per-guild intro files | ❌ git-ignored |

## Adding a new cog
1. Create `cogs/my_feature.py` with a `MyCog(commands.Cog)` class and `async def setup(bot)`.
2. Add `await bot.load_extension('cogs.my_feature')` in `bot.py`'s `main()`.
3. Add commands to `_HELP_TEXT` in `cogs/music.py` and to `help.md`.
4. Add tests in `tests/test_my_feature_cog.py`.
