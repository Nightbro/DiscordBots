# Discord Bots

A collection of Discord music bots.

---

## Bots

### 🎵 suno-bot
Plays **Suno AI songs** and **YouTube** audio in voice channels. Downloads tracks locally before playing for glitch-free audio. Includes a persistent playlist library.

### 📺 youtube-bot
Lightweight bot for playing **YouTube** audio via URL or search.

---

## suno-bot

### Features
- Play Suno songs by URL (`suno.com/song/...` or short `suno.com/s/...`)
- Play YouTube videos by URL or search term
- Downloads tracks to a local cache before playing — no streaming glitches
- Embeds ID3 tags (title, artist, album) into downloaded MP3s
- Per-server playlist library saved to disk
- Auto-start on Windows login support

### Setup
1. Copy `.env.example` to `.env` and paste your bot token
2. Run `run.bat` — it installs all dependencies automatically

```
DISCORD_TOKEN=your_token_here
```

Get a token at [discord.com/developers/applications](https://discord.com/developers/applications) → Bot → Reset Token.

### Commands

#### Playback
| Command | Description |
|---|---|
| `!play <url or search>` | Play a Suno URL, YouTube URL, or YouTube search. Alias: `!p` |
| `!skip` | Skip the current song. Alias: `!s` |
| `!pause` | Pause playback |
| `!resume` | Resume playback. Alias: `!r` |
| `!stop` | Stop playback, clear queue, disconnect |
| `!queue` | Show the current queue. Alias: `!q` |
| `!clear` | Clear the queue without stopping the current song |
| `!leave` | Disconnect from voice. Alias: `!dc` |
| `!cleanup` | Delete all cached MP3s from the downloads folder |

#### Playlist Library
| Command | Description |
|---|---|
| `!pl save <name>` | Save the current queue as a named playlist |
| `!pl load <name>` | Load a playlist into the queue |
| `!pl list` | List all saved playlists |
| `!pl show <name>` | Show tracks inside a playlist |
| `!pl add <name> <url>` | Add a track to an existing playlist |
| `!pl remove <name> <#>` | Remove a track by number |
| `!pl delete <name>` | Delete a playlist |

### Auto-start on Windows
Run `register_startup.bat` as Administrator once. The bot will start silently at every login.
To remove: `schtasks /delete /tn "SunoDiscordBot"`

### Requirements
- Python 3.10+
- FFmpeg (installed automatically by `run.bat` via winget)

---

## youtube-bot

### Setup
1. Copy `.env.example` to `.env` and paste your bot token
2. Run `run.bat`

### Commands
| Command | Description |
|---|---|
| `!play <url or search>` | Play a YouTube URL or search. Alias: `!p` |
| `!skip` | Skip the current song. Alias: `!s` |
| `!pause` | Pause playback |
| `!resume` | Resume playback. Alias: `!r` |
| `!stop` | Stop playback, clear queue, disconnect |
| `!queue` | Show the current queue. Alias: `!q` |
| `!clear` | Clear the queue |
| `!leave` | Disconnect from voice. Alias: `!dc` |
