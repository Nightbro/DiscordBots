# Night Roller — Setup & Deployment

Covers three things, in order:
1. [Creating the bot in Discord and getting your parameters](#1-discord-developer-portal--getting-your-parameters)
2. [Running it on the Raspberry Pi](#2-raspberry-pi-setup)
3. [Auto-updating on every push](#3-auto-update-on-git-push)

---

## 1. Discord Developer Portal — getting your parameters

Night Roller is a **separate Discord application** from Echo. Two bots cannot share a token — one token is one bot user. Everything below happens at <https://discord.com/developers/applications>.

### 1.1 Create the application

1. **New Application** (top right) → name it `Night Roller` → accept the terms → **Create**.
2. *(Optional)* **General Information** → upload an icon and write a description. This is what people see in the member list.

### 1.2 Create the bot user and get `DISCORD_TOKEN`

1. Left sidebar → **Bot**.
2. **Reset Token** → confirm → **Copy**. This is your `DISCORD_TOKEN`.
   - The token is shown **once**. If you lose it, reset it again (which invalidates the old one).
   - It is a password. Never commit it — `.env` is gitignored for exactly this reason.
3. Still on the **Bot** page, scroll to **Privileged Gateway Intents** and enable:
   - ✅ **Message Content Intent** — required, or `!roll` will never reach the bot
   - ❌ Presence Intent — not needed
   - ❌ Server Members Intent — not needed

   Click **Save Changes**.
4. *(Recommended)* Under **Bot**, turn **Public Bot** off if you only want to add it to your own servers.

### 1.3 Get `OWNER_ID` (your Discord user ID)

1. In the Discord **app** (not the portal): **User Settings → Advanced → Developer Mode: On**.
2. Right-click your own name anywhere → **Copy User ID**.

This gates the owner-only `!restart` command.

### 1.4 Get `DEV_GUILD_ID` (optional but recommended)

With Developer Mode on, right-click your D&D server's icon → **Copy Server ID**.

Setting this makes `/` slash commands appear in that server **instantly** on startup. Without it, Discord takes up to an hour to propagate them globally. Prefix commands (`!roll`) work either way.

### 1.5 Invite the bot to your server

1. Left sidebar → **OAuth2** → **URL Generator**.
2. **Scopes:** check `bot` and `applications.commands`.
3. **Bot Permissions:** check
   - `Send Messages`
   - `Embed Links` (every reply is an embed — without this the bot appears silent)
   - `Read Message History`
   - `Use Slash Commands`
4. Copy the **Generated URL** at the bottom, open it in a browser, pick your server, **Authorize**.

You need *Manage Server* permission on the target server to add a bot.

### 1.6 Fill in `.env`

On the Pi (or your dev machine), in `night-roller/`:

```bash
cp .env.example .env
nano .env
```

```
DISCORD_TOKEN=paste_the_token_from_step_1.2
OWNER_ID=paste_your_user_id_from_step_1.3
DEV_GUILD_ID=paste_your_server_id_from_step_1.4
```

Save (`Ctrl+X`, `Y`, `Enter`).

---

## 2. Raspberry Pi setup

### 2.1 First run

The repo is already on the Pi at `~/DiscordBots` (same clone Echo uses), so just pull and run:

```bash
cd ~/DiscordBots && git pull
```

```bash
cd ~/DiscordBots/night-roller && chmod +x run.sh auto_update.sh && ./run.sh
```

`run.sh` creates `venv/`, installs `requirements.txt`, checks `.env`, and starts the bot. No ffmpeg or PyNaCl needed — this bot never touches voice.

Test it in Discord: `!roll`, `!roll 2d6+3`, `!roll adv +5`. Then `Ctrl+C` to stop.

### 2.2 Run on startup (systemd)

`night-roller.service` assumes user `pi` and `/home/pi/DiscordBots/night-roller`. If your username or path differs, edit `User=`, `WorkingDirectory=`, `ExecStart=`, and `EnvironmentFile=` first.

```bash
sudo cp ~/DiscordBots/night-roller/night-roller.service /etc/systemd/system/
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable night-roller && sudo systemctl start night-roller
```

`enable` = start on every boot. `start` = start now. Check it came up:

```bash
systemctl status night-roller
```

Echo and Night Roller are independent services — restarting one never touches the other.

### 2.3 Logs

```bash
journalctl -u night-roller -f
```

Per-run files also land in `night-roller/data/logs/night_roller_<timestamp>.log`.

### 2.4 Start / stop / restart

```bash
sudo systemctl restart night-roller
```

```bash
sudo systemctl stop night-roller
```

**UI alternative:** taskbar → *Preferences → Task Manager* → **Services** tab → right-click `night-roller` → Start / Stop / Restart, plus a checkbox for start-on-boot.

---

## 3. Auto-update on git push

Echo's self-hosted GitHub Actions runner is already installed on the Pi and is registered for the **whole repo**, so Night Roller reuses it — there is no second runner to set up.

### 3.1 What is already done

- `~/actions-runner-discordbots` — the runner service, running for `Nightbro/DiscordBots`
- `.github/workflows/deploy.yml` — deploys **echo-bot** on pushes touching `echo-bot/**`
- `.github/workflows/deploy-night-roller.yml` — deploys **night-roller** on pushes touching `night-roller/**` (added with this bot)

Because the two workflows have separate path filters, a push that only touches `night-roller/` restarts only Night Roller, and vice versa.

### 3.2 The one thing you must do on the Pi

The runner restarts the service with `sudo`, so it needs a passwordless sudo rule for this new service — the existing rule only covers `echo-bot`:

```bash
sudo visudo
```

At the very bottom, next to the echo-bot line, add (replace `pi` if your user differs):

```
pi ALL=(ALL) NOPASSWD: /bin/systemctl restart night-roller
```

Save and exit (`Ctrl+X`, then `Y`, then `Enter`).

Without this the workflow fails at the last step with a password prompt.

### 3.3 Verify it works

1. Push any change under `night-roller/`.
2. **GitHub repo → Actions tab** → watch "Deploy Night Roller to Raspberry Pi" run its three steps.
3. In Discord, run `!version` — the commit count and hash come from the running git checkout, so a new number confirms the deploy actually landed.

### 3.4 Cron fallback (`auto_update.sh`)

If the runner is offline, `auto_update.sh` polls GitHub and updates the same way. It exits immediately when there is nothing new, so running it often is cheap.

```bash
crontab -e
```

Add (every 5 minutes):

```
*/5 * * * * /home/pi/DiscordBots/night-roller/auto_update.sh >> /home/pi/night-roller-update.log 2>&1
```

Only use one mechanism at a time as your primary — the Actions runner is the faster of the two; cron is the safety net.

---

## 4. Updating manually

```bash
cd ~/DiscordBots && git pull && sudo systemctl restart night-roller
```

If `requirements.txt` changed:

```bash
cd ~/DiscordBots/night-roller && source venv/bin/activate && pip install -r requirements.txt && sudo systemctl restart night-roller
```

---

## 5. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Bot is online but ignores `!roll` | **Message Content Intent** is off — Developer Portal → Bot → enable it → restart the service |
| Bot replies with nothing / blank messages | Missing **Embed Links** permission in that channel |
| `DISCORD_TOKEN not set in .env` on startup | `.env` missing or empty; note systemd reads it via `EnvironmentFile=`, so the path in the unit file must be right |
| `/roll` doesn't appear | Set `DEV_GUILD_ID` and restart, or wait out the global sync |
| `LoginFailure: Improper token` | Token was reset in the portal — copy the new one into `.env` |
| Deploy workflow fails on "Restart bot" | The `visudo` line from §3.2 is missing or misspelled |
| Both bots stopped after a reboot | `sudo systemctl enable night-roller` was never run |
