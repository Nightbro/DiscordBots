# Privacy Policy

**Applies to:** the Discord bots **Echo** (`echo-bot`) and **Night Roller** (`night-roller`), together "the Bots".

**Last updated:** 2026-08-28

**Contact:** `<CONTACT — replace with the email or Discord handle you want users to reach you at>`

---

## 1. Summary

The Bots are self-hosted hobby projects run by a private individual ("the Operator") on a Raspberry Pi at a private residence. There is no cloud database, no analytics, no advertising, and no third-party tracking. Nothing is sold, rented, or shared for marketing.

The Bots store the minimum needed to work: server settings, the audio you deliberately upload, and short-lived operational logs. **Neither Bot records voice channels or listens to what you say.**

## 2. What is stored

### Echo (`echo-bot`)

| Data | Where | Why |
|---|---|---|
| Discord **server (guild) IDs** | `data/guild_config.json` | Keep per-server settings: auto-join, language, TTS voice and rate, notification preferences |
| Discord **user IDs** | `data/intro_config.json` | Map a member to their personal intro sound (`user_<member_id>` keys) |
| **Audio files you upload** | `data/intro_sounds/`, `data/soundboard/` | Play back your intro sounds and soundboard entries |
| **Soundboard entries** | `data/soundboard_config.json` | Sound names, emoji, and short triggers |
| **Playlists** | `data/playlists.json` | Track titles and source URLs you chose to save, per server |
| **Cached audio** | `data/downloads/` | Avoid re-downloading the same track |
| **Operational logs** | `data/logs/` | Diagnose errors and crashes |

### Night Roller (`night-roller`)

| Data | Where | Why |
|---|---|---|
| **Operational logs** | `data/logs/` | Diagnose errors and crashes |

Night Roller stores **no persistent data at all** — no settings, no roll history, no user records. Every roll is computed in memory and forgotten.

### What logs contain

Logs may record a Discord username, a server ID, the command that was run (including a dice expression or a search term), and any resulting error and stack trace. They are plain text files on the Operator's machine and are never published or transmitted anywhere.

## 3. What is *not* stored

- **Voice audio.** Neither Bot records, saves, or transcribes anything spoken in a voice channel. Echo joins voice channels only to *play* audio. Its `!listen` command is an unimplemented placeholder that does nothing but reply with a message.
- **Message content**, other than the text of the command you send to the Bot itself.
- Passwords, payment details, email addresses, IP addresses, or Discord tokens belonging to users.
- Anything about servers the Bots are not a member of.

## 4. Legal basis and purpose

Data is processed solely to provide the features you ask for, and to keep the Bots running. It is never used for profiling, advertising, or automated decision-making, and it is not sold, rented, or disclosed to third parties for their own purposes.

## 5. Third-party services

**Both Bots** run on the Discord platform. Everything you send passes through Discord, under the [Discord Privacy Policy](https://discord.com/privacy).

**Echo** additionally contacts these services when you use the relevant feature:

| Feature | Service | What is sent |
|---|---|---|
| `!play` with a link or search term | **YouTube**, via `yt-dlp` | The URL or search text you provided |
| `!play` with a Suno link | **Suno** (`cdn1.suno.ai`) | The song ID from the URL you provided |
| `!say`, TTS notifications | **Microsoft Edge TTS** (`edge-tts`) | **The text you asked to be spoken**, sent to Microsoft's speech service to be synthesized |

The Microsoft TTS one is worth stating plainly: text you pass to `!say` leaves the Operator's machine and is processed by Microsoft. Do not send anything sensitive through it.

The Operator has no control over these services and does not receive personal data back from them.

**Night Roller** contacts no third-party service other than Discord.

## 6. Retention

| Data | Kept for |
|---|---|
| Echo — logs and cached downloads | Automatically deleted when older than **7 days** (purged on every startup) |
| Echo — settings, playlists, intro and soundboard configs | Until deleted by a user, a server admin, or the Operator |
| Echo — uploaded audio files | Until deleted via the relevant command, or by the Operator |
| Night Roller — logs | Rotating files capped at 2 MB with 3 backups; the oldest are overwritten automatically. No age-based purge, because nothing else is stored |

Data is not automatically erased when a Bot is removed from a server — ask the Operator if you want it wiped immediately.

## 7. Your choices and rights

You can delete most of your own data directly, without asking anyone:

| To remove | Use |
|---|---|
| Your personal intro sound | `!intro clear @you` |
| A soundboard sound | `!soundboard remove <name>` |
| A saved playlist | `!playlist delete <name>` |

For anything else — including a full erasure of every record tied to your user ID or your server — contact the Operator using the address at the top of this document. Requests are handled manually and honoured as promptly as reasonably possible.

Depending on where you live (for example under the GDPR), you may have rights to access, correct, export, or erase your personal data, and to object to its processing. The Operator will act on such requests in good faith. Because the Bots deliberately store so little, in most cases the answer is that no data about you exists beyond a server ID or a short-lived log line.

## 8. Security

Data lives on a private, password-protected home machine. Bot tokens are kept in a `.env` file that is excluded from version control and never committed to the public repository.

That said: this is a hobby project on consumer hardware, not a hardened production system. No method of storage or transmission is perfectly secure, and no guarantee of absolute security is offered.

## 9. Children

The Bots are not directed at children under the minimum age required by [Discord's Terms of Service](https://discord.com/terms) in their country. The Operator does not knowingly collect data from anyone below that age. If you believe a child's data has been stored, contact the Operator and it will be deleted.

## 10. Changes

This policy may change. The current version always lives in this repository, and the "Last updated" date reflects the latest change. Material changes will be noted in the repository's commit history, which is public.

---

*This is a plain-language policy for a hobby project, not legal advice. If the Bots ever grow beyond personal use, have it reviewed by a qualified lawyer.*
