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
| `!play <url\|search\|name\|#N>` | `!p` | Add a track to the queue and start playback. A name matching an uploaded track plays that, after a 5-second prompt offering a YouTube search instead |
| `!skip` | `!s` | Skip the current track |
| `!pause` | — | Pause playback |
| `!resume` | `!unpause` | Resume playback |
| `!stop` | — | Stop playback and clear the queue |
| `!replay` | `!rp` | Restart the current track from the beginning |
| `!nowplaying` | `!np` | Show the currently playing track |
| `!join` | — | Join your voice channel |
| `!leave` | `!disconnect`, `!dc` | Leave the voice channel and clear all state |

---

## Library (uploaded tracks)

Songs uploaded to the bot and kept on the server, so nothing depends on an outside site. Each server has its own library; anyone can add or remove.

| Command | Aliases | Description |
|---|---|---|
| `!save [name]` | `!upload` | Save the attached audio file to this server's library. Works on a reply to a message with an attachment. Name defaults to the filename |
| `!library` | `!lib` | Browse the library: numbered list, a dropdown to play, page buttons |
| `!library <name\|#N>` | `!lib` | Play a track straight away |
| `!lib play <name\|#N>` | — | Same, spelled out |
| `!lib remove <name\|#N>` | `!lib delete` | Remove a track and delete its file |
| `!lib rename <name\|#N> <new name>` | — | Rename a track |
| `!lib info <name\|#N>` | — | Length, size, who added it, play count |

`#N` is the number shown by `!library`. Limits per server: 100 tracks, 2048 MB — both in `config.yaml`, along with `confirm_secs` for the `!play` prompt (set it to 0 to play uploads without asking). Supported formats: mp3, ogg, wav, flac, m4a, opus, aac. Discord caps uploads at 10 MB on unboosted servers.

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

Per-trigger intro sounds for bot join, any-user join, and per-member join events.
Supported formats: `.mp3` `.ogg` `.wav` `.flac` `.m4a` `.opus` `.aac`

**Trigger:** `bot` · `user` · `@mention`

| Command | Description |
|---|---|
| `!intro set <trigger>` | Set the default intro for a trigger (attach audio or provide URL) |
| `!intro schedule <trigger> <days>` | Set a day-specific intro — e.g. `MON-FRI`, `WEEKDAY`, `SAT,SUN` |
| `!intro unschedule <trigger> <days>` | Remove a day-specific override |
| `!intro clear <trigger>` | Remove all intros for a trigger |
| `!intro rename <trigger> <name>` | Set a human-readable label for a trigger's default |
| `!intro list` | List all configured triggers for this server |
| `!intro show` | Show bot/user overview and global flags |
| `!intro trigger <trigger>` | Manually play an intro right now |
| `!intro autojoin on\|off` | Toggle bot auto-join when the first user enters a channel |

**Days:** `MON` `TUE` ... `SAT,SUN` `MON-FRI` `WEEKDAY` `WEEKEND` `*`
**Priority (schedule):** matching day override → default

---

## Soundboard

| Command | Description |
|---|---|
| `!sb add <name> 💥 [short]` | Add a sound (attach audio file). Emoji separates name from optional short. Auto-short is name with spaces removed. |
| `!sb remove <name>` | Remove a sound and delete its file |
| `!sb play <name>` | Play a sound in your voice channel |
| `!sb short <name> <short>` | Change the short trigger for an existing sound |
| `!sb list` | List all sounds with their emojis |
| `!sb panel` | Post a reaction panel — react to play sounds |

Alias: `!soundboard`

> **`sb add`** — emoji is required and acts as a delimiter: everything before it is the name, everything after is the short. No quotes needed for multi-word names.
> Examples: `!sb add explosion effect 💥` → auto-short `explosioneffect` · `!sb add explosion effect 💥 ex` → short `ex`
>
> **`sb short`** — put the new short last, everything before it is the name. No quotes needed.
> Example: `!sb short explosion effect ex` → sets short to `ex`

**Quick trigger:** Type `!<name>` or `!<short>` directly (e.g. `!explosioneffect` or `!ex`) to play a sound. Case-insensitive. Unknown names are silently ignored.

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
| `notify_say_text` | `false` | Send embed after `!say` completes (off by default — reacts with ✅ instead) |
| `notify_say_voice` | `false` | Speak the "Speaking." confirmation after `!say` completes |

**Notification modes** (`notify_write` + `notify_say`):
- Both on: sends a text embed **and** speaks the response
- Write only (default): sends a text embed — silent
- Say only: reacts with ✅ / ❌ / ❓ to your message and speaks the response
- Both off: only reacts with ✅ / ❌ / ❓ — fully silent

**Song detail notifications** (`notify_song_text` + `notify_song_voice`) are independent of the above:
- `notify_song_text` controls only the `!play` track card — not other command responses
- `notify_song_voice` controls only speaking the song title — not other TTS responses
- These two settings bypass `notify_write` and `notify_say` entirely

**Say command notifications** (`notify_say_text` + `notify_say_voice`) are also independent:
- `notify_say_text` off (default): `!say` reacts with ✅ after speaking — no embed sent
- `notify_say_voice` controls whether the "Speaking." confirmation is spoken after the text — the user's text is always spoken regardless
- These two settings bypass `notify_write` and `notify_say` entirely

---

## Dev log (Manage Server)

Forward this server's errors (WARNING and above, with a short traceback) to a channel or your DMs. Each server opts in on its own and only sees its own errors. Entries are batched, at most one message every few seconds.

| Command | Description |
|---|---|
| `!devlog` | Show whether the dev log is on for this server, and where it goes |
| `!devlog here` | Send this server's errors to the channel you type it in |
| `!devlog dm` | Send this server's errors to your DMs |
| `!devlog off` | Turn the dev log off for this server |
| `!devlog test` | Log a test entry to check it arrives |
| `!devlog here all` / `!devlog dm all` | *(bot owner)* Also include errors not tied to any server (startup, connection, cog loading) |
| `!devlog here` *(in a DM with the bot)* | *(bot owner)* Get **every** error from **every** server in that DM; `!devlog off` there stops it |

Settings are stored in `data/devlog_config.json` and survive restarts.

---

## Dev (owner only)

| Command | Description |
|---|---|
| `!reload <cog>` | Hot-reload a cog (also reloads all utils) |
| `!restart` | Shut down the bot (PM2 auto-restarts) |
| `!sync [guild_id]` | Push slash commands to Discord (global or guild-specific) |
| `!status` | Show bot status: guilds, voice connections, loaded cogs |
| `!cogs` | List all loaded extensions |
