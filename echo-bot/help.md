# Echo Bot — Command Reference

All commands work with `!` prefix and as `/` slash commands.

---

## Help

| Command | Description |
|---|---|
| `!help` | Show paginated help (overview + all sections) |
| `!help <section>` | Jump directly to a section: `music`, `queue`, `intros`, `soundboard`, `tts` |

---

## Music — Playback

| Command | Aliases | Description |
|---|---|---|
| `!play <url\|search>` | `!p` | Add a track to the queue and start playback |
| `!skip` | `!s` | Skip the current track |
| `!pause` | — | Pause playback |
| `!resume` | `!unpause` | Resume playback |
| `!stop` | — | Stop playback and clear the queue |
| `!nowplaying` | `!np` | Show the currently playing track |
| `!join` | — | Join your voice channel |
| `!leave` | `!disconnect`, `!dc` | Leave the voice channel and clear all state |

---

## Music — Queue & Playlists

| Command | Aliases | Description |
|---|---|---|
| `!queue [page]` | `!q` | Show the playback queue |
| `!clear` | — | Clear the queue (keeps current track playing) |
| `!remove <#>` | `!rm` | Remove a track by its position number |
| `!shuffle` | — | Shuffle the queue |
| `!playlist save <name>` | `!pl save` | Save the current queue as a named playlist |
| `!playlist load <name>` | `!pl load` | Load a playlist into the queue |
| `!playlist list` | `!pl list` | List all saved playlists |
| `!playlist delete <name>` | `!pl delete` | Delete a saved playlist |
| `!playlist show <name>` | `!pl show` | Show the contents of a playlist |

---

## Intros

Per-user intro sounds that play when you join a voice channel.
Supported formats: `.mp3` `.ogg` `.wav` `.flac` `.m4a` `.opus` `.aac`

| Command | Description |
|---|---|
| `!intro set` | Set your default intro sound (attach audio file) |
| `!intro schedule <days>` | Set an intro for specific days — e.g. `mon,fri` or `monday,friday` |
| `!intro override <YYYY-MM-DD>` | Set a one-off intro for a specific date |
| `!intro unschedule <days>` | Remove scheduled days |
| `!intro clear` | Remove all your intro settings |
| `!intro show` | Show your current intro config |
| `!intro list` | List all intro configs on this server |
| `!intro trigger` | Play your intro sound right now |
| `!intro autojoin <true\|false>` | Toggle whether the bot auto-joins your channel |

**Priority:** date override → weekday schedule → default

---

## Soundboard

| Command | Description |
|---|---|
| `!sb add <name> [emoji]` | Add a sound (attach audio file). Auto-assigns an emoji if omitted. |
| `!sb remove <name>` | Remove a sound and delete its file |
| `!sb play <name>` | Play a sound in your voice channel |
| `!sb list` | List all sounds with their emojis |
| `!sb panel` | Post a reaction panel — react to play sounds |

Alias: `!soundboard`

---

## TTS

Text-to-speech via Microsoft Edge TTS. Speaks in your voice channel, pausing any music playback while speaking.

| Command | Description |
|---|---|
| `!say <text>` | Speak text in your voice channel |
| `!tts voice <name>` | Set the TTS voice for this server |
| `!tts voices [locale]` | List available voices, optionally filtered by locale (e.g. `en`, `sr`) |
| `!tts rate <+N%\|-N%>` | Set speech rate — e.g. `+10%` faster, `-20%` slower |
| `!tts stop` | Stop TTS currently speaking |
| `!tts show` | Show current voice and rate for this server |

Default voice: `en-US-AriaNeural` (set in `config.yaml`)

---

## Settings (admins only)

Per-server overrides for bot behaviour. Values marked *(overridden)* differ from the global `config.yaml` default.

| Command | Description |
|---|---|
| `!settings` | Show current settings for this server |
| `!settings show` | Same as above |
| `!settings set <key> <true\|false>` | Override a setting for this server |
| `!settings reset <key>` | Revert a setting to the global default |

**Available keys:**

| Key | Default | Description |
|---|---|---|
| `auto_join` | `false` | Join a voice channel when the first person enters it |
| `auto_leave` | `true` | Leave when the last person exits the bot's channel |
| `notify_write` | `true` | Send a text message for command responses |
| `notify_say` | `false` | Speak responses via TTS when bot is in voice |
| `notify_song_text` | `true` | Show track card embed when a song is loaded via `!play` |
| `notify_song_voice` | `false` | Speak track title via TTS when a song is loaded via `!play` |

**Notification modes** (`notify_write` + `notify_say`):
- Both on: sends a text embed **and** speaks the response
- Write only (default): sends a text embed — silent
- Say only: reacts with ✅ / ❌ / ❓ to your message and speaks the response
- Both off: only reacts with ✅ / ❌ / ❓ — fully silent

**Song detail notifications** (`notify_song_text` + `notify_song_voice`) are independent of the above:
- `notify_song_text` controls only the `!play` track card — not other command responses
- `notify_song_voice` controls only speaking the song title — not other TTS responses
- These two settings bypass `notify_write` and `notify_say` entirely

---

## Dev (owner only)

| Command | Description |
|---|---|
| `!reload <cog>` | Hot-reload a cog (also reloads all utils) |
| `!restart` | Shut down the bot (PM2 auto-restarts) |
| `!sync [guild_id]` | Push slash commands to Discord (global or guild-specific) |
| `!status` | Show bot status: guilds, voice connections, loaded cogs |
| `!cogs` | List all loaded extensions |
