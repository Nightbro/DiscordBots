# Discord Bots

A collection of Discord bots.

![Deploy to Pi](https://github.com/Nightbro/DiscordBots/actions/workflows/deploy.yml/badge.svg)

---

## Bots

### 🔊 echo-bot
Full-featured audio bot: music playback, soundboard, per-user intro sounds, and TTS. Runs on Raspberry Pi with auto-deploy via GitHub Actions.

See [`echo-bot/LINUX_SETUP.md`](echo-bot/LINUX_SETUP.md) for setup and deployment guide.

### Features
- Play YouTube audio by URL or search
- Suno AI song playback
- Per-user intro sounds (on voice join)
- Soundboard with reaction panel
- Text-to-speech via edge-tts
- Per-server settings and playlists
- Auto-deploy to Raspberry Pi on every push

---

### 🎲 night-roller
Dice bot for D&D. `!roll` rolls a d20; `!roll 2d6+3`, `!roll adv +5`, and multi-group expressions all work, as prefix or slash commands. Runs on the same Raspberry Pi with its own auto-deploy.

See [`night-roller/LINUX_SETUP.md`](night-roller/LINUX_SETUP.md) for the Discord app walkthrough, Pi setup, and auto-update guide, and [`night-roller/help.md`](night-roller/help.md) for the command reference.

### Features
- `!roll` with full dice expressions: `d20`, `2d6+3`, `d20+2d4+1`, `2d6-1d4`
- Advantage / disadvantage (`!roll adv`, `!roll dis`)
- Natural 20 and natural 1 called out
- Optional free-text label on any roll (`!roll 2d6+3 sneak attack`)
- Auto-deploy to Raspberry Pi on every push

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

Both cover Echo and Night Roller. Link them in the Discord Developer Portal under **General Information → Terms of Service URL / Privacy Policy URL** for each application.
