# Discord Bots

A collection of Discord bots.

![Deploy to Pi](https://github.com/Nightbro/DiscordBots/actions/workflows/deploy.yml/badge.svg)

---

## Bots

### 🔊 echo-bot
Full-featured audio bot: music playback, soundboard, per-user intro sounds, and TTS. Runs on Raspberry Pi with auto-deploy via GitHub Actions.

See [`echo-bot/LINUX_SETUP.md`](echo-bot/LINUX_SETUP.md) for setup and deployment guide,
[`echo-bot/FEATURES.md`](echo-bot/FEATURES.md) for the full feature list, and
[`echo-bot/help.md`](echo-bot/help.md) for the command reference.

#### Features
- Play YouTube audio by URL or search
- Per-server library of uploaded tracks (`!save`, `!library`), played by name or number
- Per-user intro sounds (on voice join)
- Soundboard with reaction panel and multi-word quick triggers
- Text-to-speech via edge-tts
- Per-server settings and playlists
- Dev log: per-server error forwarding to a channel or DM
- Auto-deploy to Raspberry Pi on every push

Suno playback was removed in November 2026 — see [`echo-bot/FEATURES.md`](echo-bot/FEATURES.md#withdrawn).

---

### 🎲 night-roller
Dice bot for D&D. `!roll` rolls a d20; `!roll 2d6+3`, `!roll adv +5`, and multi-group expressions all work, as prefix or slash commands. Runs on the same Raspberry Pi with its own auto-deploy.

**Superseded by Chronicler**, which has absorbed its dice. Night Roller stays here and keeps running until Chronicler is deployed and verified, then it will be retired. Do not add both to the same server — they both answer `!roll`.

See [`night-roller/LINUX_SETUP.md`](night-roller/LINUX_SETUP.md) for the Discord app walkthrough, Pi setup, and auto-update guide, and [`night-roller/help.md`](night-roller/help.md) for the command reference.

#### Features
- `!roll` with full dice expressions: `d20`, `2d6+3`, `d20+2d4+1`, `2d6-1d4`
- Advantage / disadvantage (`!roll adv`, `!roll dis`)
- Natural 20 and natural 1 called out
- Optional free-text label on any roll (`!roll 2d6+3 sneak attack`)
- Auto-deploy to Raspberry Pi on every push

---

### 🕯️ chronicler
Tabletop chronicle keeper, aimed at Chronicle of Darkness. Four responsibilities: dice, announcements and reminders, a character builder, and session notes. **Dice are built; the other three are planned** — see [`chronicler/FEATURES.md`](chronicler/FEATURES.md) for what works today and [`chronicler/ARCHITECTURE.md`](chronicler/ARCHITECTURE.md) for how it is put together.

No Discord application exists for it yet, so it is not deployed. See [`chronicler/LINUX_SETUP.md`](chronicler/LINUX_SETUP.md) for what remains, and [`chronicler/help.md`](chronicler/help.md) for the command reference.

#### Features
- `!roll` with full dice expressions, advantage/disadvantage and free-text labels, ported from Night Roller
- Success-counting dice pools: `!roll 5 (6)`, or automatic scoring in World of Darkness servers
- `!archive run` exports a channel's messages, images and files to a zip that opens in a browser
- Exports keep attachments exactly as uploaded and reference them locally, since Discord's own links expire within a day
- Every export carries a manifest of the message IDs it saved — the interlock for clearing a channel safely
- Per-server settings via `!config` — roll system, default die, difficulty, botch rule
- Paginated `!help` that adapts to the server's roll system
- A feature list and command reference that the test suite refuses to let drift
- Atomic JSON writes, so a crash mid-save cannot truncate stored data

---

## Setup
1. Copy `.env.example` to `.env` in the bot's folder and fill in your token
2. Run `run.sh` (Linux/Pi) or `run.bat` (Windows)

```
DISCORD_TOKEN=your_token_here
OWNER_ID=your_discord_user_id
```

Get a token at [discord.com/developers/applications](https://discord.com/developers/applications) → Bot → Reset Token. Each bot needs its own application and token.

---

## Legal

- [Terms of Service](TERMS_OF_SERVICE.md)
- [Privacy Policy](PRIVACY_POLICY.md)

They cover Echo, Night Roller and Chronicler. Link them in the Discord Developer Portal under **General Information → Terms of Service URL / Privacy Policy URL** for each application.
