# Chronicler — Setup and Deployment

Keep this file current. Whenever a feature needs a new Discord permission or a
new piece of configuration, it is recorded here in the same change.

> **Status:** no Discord application exists for Chronicler yet, so it is not
> deployed anywhere. The permissions below are what it will need; the steps for
> creating the application and deploying to the Pi are written out but have not
> been walked through.

---

## 1. Permissions the bot needs

Set these under **OAuth2 → URL Generator** in the
[Developer Portal](https://discord.com/developers/applications). Tick the
checkboxes rather than pasting a permissions number — a number nobody can read
drifts out of step with the list silently.

### Scopes

| Scope | Why |
|---|---|
| `bot` | It is a bot |
| `applications.commands` | Every command also works as a `/` slash command |

### Bot permissions

| Permission | Needed for |
|---|---|
| View Channel | Seeing any channel at all |
| Send Messages | Every reply |
| Embed Links | Every reply is an embed |
| Read Message History | `!` prefix commands, and reading a channel for an export |
| Attach Files | Delivering an archive bundle into the channel |
| Manage Messages | **Not yet** — only when clearing an archived channel lands |

Chronicler needs no voice permissions. It never joins a voice channel.

Keep Manage Messages **off** until the clearing feature exists. There is no
reason to hold a deletion permission the bot cannot use.

### Privileged intents

Under **Bot → Privileged Gateway Intents**, enable:

| Intent | Why |
|---|---|
| Message Content Intent | Reading command text, and reading message bodies for an export |

Server Members and Presence are **not** needed.

### Per-channel permissions

Guild-wide permissions are not enough on their own. To export a channel the bot
must also be able to see it — a private channel needs the bot's role (or the bot
itself) added to that channel's permission overwrites with View Channel and Read
Message History. The export refuses with a clear message naming what is missing
rather than failing halfway.

### After generating the URL

Paste the generated invite URL into `invite_url` in `config.yaml`. Until it is
set, DMing the bot `join` replies that there is no link yet instead of sending a
broken one.

---

## 2. Configuration

### .env — secrets only, never committed

Copy `.env.example` to `.env` and fill in:

```
DISCORD_TOKEN=     # Bot → Reset Token
OWNER_ID=          # your Discord user id (enables owner-only commands)
DEV_GUILD_ID=      # optional: a test server that gets slash commands instantly
```

Without `DEV_GUILD_ID`, global slash commands propagate on Discord's own
schedule, which can take up to an hour. `!sync` pushes them manually.

### config.yaml — everything else

`bot:` is identity (name, prefix, colour, emojis, invite URL). `dice:` is roll
defaults and limits. `archive:` bounds exports and sets how transcripts look:

| Key | Default | Meaning |
|---|---|---|
| `max_messages` | 20000 | Largest export, refused before downloading |
| `max_bundle_mb` | 1024 | Most attachment bytes in one export |
| `image_width` | 480 | Display width of images in `index.html` |
| `retention_days` | 0 | **0 means bundles are never auto-deleted** |
| `confirm_secs` | 60 | How long a deletion confirmation stays live |
| `progress_every` | 250 | Edit the progress message every N messages |

`retention_days` defaults to off on purpose. A bundle can be the only remaining
copy of a cleared channel, so deleting backups by age has to be a choice
somebody makes deliberately.

---

## 3. Running it

The test suite needs no token:

```bash
cd chronicler
python -m pytest
```

To start the bot, put a token in `.env`, then `./run.sh` on Linux or `run.bat`
on Windows. Both create the virtualenv and install dependencies on first run.

Dependencies are all pure-Python wheels — `discord.py`, `python-dotenv`,
`certifi`, `pyyaml`, `fpdf2`, `python-docx`, `Pillow` — so no `apt` packages are
needed and the deploy can install everything itself.

---

## 4. Deploying to the Raspberry Pi

Assumes the repo at `/home/pi/DiscordBots` and the other bots already running.

```bash
cd /home/pi/DiscordBots/chronicler
cp .env.example .env && nano .env        # paste the token
./run.sh                                 # first run: builds venv, installs deps
```

Once it starts cleanly, stop it and install the service:

```bash
sudo cp chronicler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable chronicler
sudo systemctl start chronicler
sudo systemctl status chronicler
journalctl -u chronicler -f
```

Logs also land in `data/logs/chronicler_<timestamp>.log`.

### Auto-deploy on push

`.github/workflows/deploy-chronicler.yml` runs on any push touching
`chronicler/**`: it pulls, installs dependencies and restarts the service. The
self-hosted runner is registered for the whole repository, so **no new runner is
needed** for a third bot.

It needs one `sudoers` line so the runner may restart the service without a
password:

```
pi ALL=(ALL) NOPASSWD: /bin/systemctl restart chronicler
```

Add it with `sudo visudo`, alongside the equivalent lines for the other bots.

Until the service exists on the Pi, that workflow will fail at the dependency
step — it has nothing to install into and nothing to restart. That is expected
and harms nothing; the other bots are untouched.

### Cron fallback

`auto_update.sh` polls git and restarts if anything changed, for when the
runner is down:

```
*/5 * * * * /home/pi/DiscordBots/chronicler/auto_update.sh >> /home/pi/chronicler-update.log 2>&1
```

---

## 5. Note on Night Roller

Chronicler supersedes Night Roller and answers the same `!roll`. Do not add both
to one server — they will both reply. Night Roller keeps running until
Chronicler is deployed and verified, then it gets retired.

---

## 6. Troubleshooting

| Symptom | Cause |
|---|---|
| `DISCORD_TOKEN not set in .env` | No `.env`, or the variable is empty |
| Slash commands missing | No `DEV_GUILD_ID`; wait, or run `!sync` |
| `!version` shows an old hash | The restart did not take — check `systemctl status` |
| Export says it needs View Channel | The bot is not in that channel's overwrites |
| Export says it needs Read Message History | Missing from the invite, or denied per-channel |
| Bundle not attached to the reply | Larger than the server's upload limit; collect it from the reported path |
| `!archive seed` does nothing | Owner-only — `OWNER_ID` must match your user id |
