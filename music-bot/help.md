# Music Bot — Command Reference

## Playback

| Command | Alias | Description |
|---|---|---|
| `!join` | `!j` | Join your voice channel without playing anything. |
| `!play <url / search>` | `!p` | Play from YouTube, Suno, or a search query. Queues if something is already playing. |
| `!skip` | `!s` | Skip the current song. |
| `!pause` | — | Pause playback. |
| `!resume` | `!r` | Resume paused playback. |
| `!stop` | — | Stop playback, clear the queue, and disconnect. |
| `!queue` | `!q` | Show the current playback queue. |
| `!clear` | — | Clear the queue without stopping the current song. |
| `!leave` | `!dc` | Disconnect from the voice channel. |
| `!cleanup` | — | Delete all cached audio files to free up disk space. |

## Playlists (`!playlist` / `!pl`)

| Command | Description |
|---|---|
| `!pl save <name>` | Save the current queue as a named playlist. |
| `!pl load <name>` | Load a playlist into the queue and start playing. |
| `!pl list` | List all saved playlists. |
| `!pl show <name>` | Show all tracks in a playlist. |
| `!pl add <name> <url>` | Add a track to an existing playlist. |
| `!pl remove <name> <number>` | Remove a track from a playlist by its number. |
| `!pl delete <name>` | Delete a playlist entirely. |

## Intro Sounds (`!intro` / `!in`)

| Command | Description |
|---|---|
| `!intro set bot\|user\|@user <url>` | Set the **default** intro. Attach an MP3 **or** provide a YouTube/Suno/search URL. |
| `!intro schedule bot\|user\|@user <days> <url>` | Set a **day-specific override** intro. Played instead of the default on matching days. |
| `!intro unschedule bot\|user\|@user <days>` | Remove a day-specific override. |
| `!intro clear bot\|user\|@user` | Remove all intros for this trigger (default + all day overrides). |
| `!intro list` | List all configured intro triggers for this server (with source info and schedules). |
| `!intro show` | Show bot/server-wide config and which global triggers are enabled. |
| `!intro rename bot\|user\|@user <name>` | Give an intro a human-readable label shown in `!intro list`. |
| `!intro trigger bot\|user\|@user` | Manually play an intro — `bot` for the bot-join intro, `user` for the server-wide user intro, or @mention for a specific member. |
| `!intro autojoin on\|off` | Enable/disable auto-joining when the first user enters a voice channel. |

### Day patterns for `!intro schedule` / `!intro unschedule`

| Pattern | Meaning |
|---|---|
| `MON` `TUE` `WED` `THU` `FRI` `SAT` `SUN` | Single day |
| `SAT,SUN` | Comma-separated list |
| `MON-FRI` | Inclusive range (low→high only) |
| `WEEKDAY` | Alias for `MON-FRI` |
| `WEEKEND` | Alias for `SAT,SUN` |
| `*` | Every day (same as no override) |

### Intro behaviour
- **Bot join** — plays once when the bot connects to a voice channel, before the first song.
- **User join** — plays when a user joins the channel the bot is already in.
- **Day overrides** — on matching days, the day-specific file is played instead of the default. First matching schedule entry wins.
- Priority order for user-join intros: per-user (`!intro set @user`) → server-wide (`!intro set user`) → `.env` `INTRO_MP3` fallback.
- `INTRO_ON_BOT_JOIN` and `INTRO_ON_USER_JOIN` in `.env` act as global on/off switches.
- **Auto-join** (`!intro autojoin on`) — bot connects automatically when the first non-bot member joins any voice channel it isn't already in. Setting is per-server and persisted in `intro_config.json`.

## Soundboard (`!soundboard` / `!sb`)

| Command | Description |
|---|---|
| `!sb add <name> <emoji> [url/search]` | Add a sound. Attach an MP3 **or** provide a YouTube/Suno/search URL. |
| `!sb remove <name>` | Remove a sound and delete its file. |
| `!sb trigger <name>` | Play a sound (bot must be idle in voice). |
| `!sb list` | List all sounds configured for this server. |

### Soundboard behaviour
- Sounds are per-server and stored persistently.
- `!sb trigger` uses the same voice rules as `!intro trigger`: user must be in a voice channel, and if the bot is already playing audio, the command is rejected.

## Sources supported by `!play`, `!intro set`, and `!sb add`
- YouTube URLs and short links (`youtu.be/…`)
- YouTube search queries (e.g. `!play never gonna give you up`)
- Suno song URLs (`suno.com/song/…` or `app.suno.ai/s/…`)
