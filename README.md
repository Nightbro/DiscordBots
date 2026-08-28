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

### Setup
1. Copy `.env.example` to `.env` and fill in your token
2. Run `run.sh` (Linux/Pi) or `run.bat` (Windows)

```
DISCORD_TOKEN=your_token_here
OWNER_ID=your_discord_user_id
```

Get a token at [discord.com/developers/applications](https://discord.com/developers/applications) → Bot → Reset Token.
