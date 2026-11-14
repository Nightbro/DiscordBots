# Chronicler — Setup and Deployment

> **Status: not written yet.** Creating the Discord application, choosing its
> permissions and intents, deploying to the Raspberry Pi, and the runbook for
> moving Chronicler to a different server are the next task. This file is a
> placeholder rather than a copy of Night Roller's guide, because copying it
> would state things about Chronicler that are not true yet — there is no
> application, no token and no client ID.

## What already exists

The deployment plumbing is in place and mirrors the other two bots:

| File | Purpose |
|---|---|
| `chronicler.service` | systemd unit — expects the repo at `/home/pi/DiscordBots` and a venv at `chronicler/venv` |
| `../.github/workflows/deploy-chronicler.yml` | Pulls, installs deps and restarts on any push touching `chronicler/**` |
| `auto_update.sh` | Cron fallback — polls git, pulls, restarts |
| `run.sh` / `run.bat` | First-run setup and launch for Linux and Windows |

The self-hosted Actions runner is registered for the whole repository, so
Chronicler needs **no new runner** — only the workflow file above, which is
already committed.

## What is still missing

- A Discord application, bot user and token.
- The intents the bot needs (it uses `message_content`; the Developer Portal
  gate for that has to be switched on).
- The OAuth2 invite URL, which goes into `invite_url` in `config.yaml`. Until
  it is set, DMing the bot `join` replies that there is no link yet.
- `.env` on the target machine, from `.env.example`.
- The `sudoers` NOPASSWD line that lets the runner restart the service.
- The cron entry, if the fallback updater is wanted alongside Actions.

## Running it locally in the meantime

The test suite needs no token:

```bash
cd chronicler
python -m pytest
```

To start the bot you need a token in `.env` first; then `./run.sh` on Linux or
`run.bat` on Windows.

## Note on Night Roller

Chronicler supersedes Night Roller and answers the same `!roll` command. Do
not add both to the same Discord server — they will both reply. Night Roller
stays running until Chronicler is deployed and verified, then gets retired.
