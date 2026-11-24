# Echo — Features

The always-current feature list. **This file is enforced, not aspirational:**
`tests/test_help_cog.py` fails the suite if a command exists that this file does
not name, or if this file names a command that no longer exists.

Updating it is mandatory whenever a command is added, removed or renamed.

---

## Status

| Area | State |
|---|---|
| Music playback (YouTube, search) | **Shipped** |
| Uploaded track library | **Shipped** |
| Queue and playlists | **Shipped** |
| Per-user intro sounds | **Shipped** |
| Soundboard | **Shipped** |
| Text-to-speech | **Shipped** |
| Per-server settings | **Shipped** |
| Dev log | **Shipped** |
| Suno playback | **Withdrawn** — see below |
| Voice listening (trigger phrases) | Planned |

---

## Shipped

### Music playback

| Command | Feature |
|---|---|
| `!play <url>` | Play a YouTube link |
| `!play <search>` | Search YouTube and play the first result |
| `!play <name>`, `!play #N` | Play a track from this server's library (see below) |
| `!skip`, `!pause`, `!resume`, `!stop` | Playback control |
| `!replay` | Restart the current track |
| `!nowplaying` | Show the current track with elapsed time |
| `!join`, `!leave` | Move the bot in and out of voice |

- Playback is interruptible: intros, soundboard sounds and TTS cut in and the
  music resumes from the exact position it was paused at.
- FFmpeg's errors are captured, so a track that dies silently still reports why.

### Uploaded track library

Songs uploaded to the bot and kept on the Pi, so playback depends on nothing
outside this repo.

| Command | Feature |
|---|---|
| `!save [name]` | Store an attached — or replied-to — audio file |
| `!download <url\|search>`, `!download play` | Download from YouTube and save to library; prompts when a similar track exists |
| `!library` | Browse: numbered list, dropdown picker, page buttons |
| `!library <name\|#N>`, `!lib play` | Play an uploaded track |
| `!lib radio` | Shuffle all library tracks into the queue and start playing |
| `!lib radio all` | Same, also includes the downloads cache |
| `!lib remove`, `!lib rename`, `!lib info` | Manage entries |

- One library per server; no server sees another's uploads.
- `!play <name>` prefers a matching upload, offering a few seconds to switch to
  a YouTube search instead. `!play #N` plays at once.
- Per-server caps on track count and total size, both in `config.yaml`.

### Queue and playlists

| Command | Feature |
|---|---|
| `!queue [page]` | Paginated queue with the current track on top |
| `!remove <n>`, `!clear`, `!shuffle` | Queue editing |
| `!playlist save`, `!playlist load` | Save the queue, load it back |
| `!playlist list`, `!playlist show`, `!playlist delete` | Browse and manage playlists |

### Intros

| Command | Feature |
|---|---|
| `!intro set`, `!intro clear` | Set or clear your join sound |
| `!intro show`, `!intro list` | Your sound, and everyone's |
| `!intro rename`, `!intro trigger` | Rename a sound, change what triggers it |
| `!intro schedule`, `!intro unschedule` | Day-of-week scheduling for a sound |
| `!intro autojoin` | Whether the bot plays its own sound on joining |

### Soundboard

| Command | Feature |
|---|---|
| `!sb add <name> [emoji] [\| short]` | Add a sound; only the name is required and it may contain spaces |
| `!sb remove <name>`, `!sb short <name> <short>`, `!sb list` | Manage sounds and their short triggers |
| `!sb play <name>` | Play a sound immediately |
| `!sb panel` | Reaction panel — react to play |
| `!<name>` / `!<short>` | Quick trigger, multi-word names included |

- Sounds added without an emoji get a free one from a pool, so panel reactions
  stay unambiguous.

### Text-to-speech

| Command | Feature |
|---|---|
| `!say <text>` | Speak text in voice via edge-tts |
| `!tts voice`, `!tts voices` | Pick a voice, or list what is available |
| `!tts rate`, `!tts show` | Speaking rate, and the current settings |
| `!tts stop` | Stop speaking immediately |

### Per-server settings

| Command | Feature |
|---|---|
| `!settings`, `!settings show` | Current settings for this server |
| `!settings set <key>`, `!settings reset <key>` | Toggle a setting, or revert it to the default |
| `!settings locale <code>` | Display language (`en`, `sr`) |
| `!settings voice_language <code>` | TTS voice language |

- Responses can be delivered as embeds, spoken over TTS, or reduced to a
  reaction, per server.

### Dev log

| Command | Feature |
|---|---|
| `!devlog here\|dm\|off\|test` | Forward this server's errors to a channel or DM |
| `!devlog here all` | *(owner)* Include errors not tied to any server |
| `!devlog tail [level] [n]` | *(owner)* Show last N log records at or above level; inline embed or file upload |

- Each server opts in separately and sees only its own errors, batched and
  rate-limited. This is how the voice-server DNS failure on the Pi was found.
- `!devlog tail` levels: `critical`, `error` (default), `warning`, `info`, `debug`, `all`. Reads the
  errors-only log for WARNING+ levels; the full debug log for INFO/DEBUG/all.

### Help and housekeeping

| Command | Feature |
|---|---|
| `!help [section]` | Paginated help with buttons, English and Serbian |
| `!version` | Running version: base version, commit count, commit hash |
| `!listen` | Placeholder — replies that voice listening is not implemented |
| `!reload`, `!restart`, `!sync`, `!status`, `!cogs` | *(owner)* Maintenance |

---

## Withdrawn

### Suno playback

Suno links worked through three successive changes in November 2026 and then
stopped: the old CDN path began refusing every song, their current audio file
is scrambled client-side, and songs without a rendered share video have no
playable source at all. Their terms also prohibit retrieving audio outside
Suno's own download channel. The uploaded track library replaces it — download
from Suno, then `!save` the file.

---

## Planned

### Voice listening — trigger phrases

Play a sound when the bot hears a chosen word or phrase. Not started; the
blockers are known and worth writing down:

- discord.py cannot receive voice. This needs the experimental
  `discord-ext-voice-recv` extension or a move to py-cord.
- Keyword spotting (openWakeWord or a small Vosk model) is the realistic
  approach on a Pi; full transcription is too slow for several speakers at once.
  CPU, not RAM, is the binding constraint, since ffmpeg is already decoding for
  playback.
- Serbian trigger phrases are much weaker served than English ones.
- `PRIVACY_POLICY.md` currently promises that neither bot listens to or
  transcribes voice. It must be rewritten before any of this ships, and
  listening should be opt-in per server and announced in the channel.
