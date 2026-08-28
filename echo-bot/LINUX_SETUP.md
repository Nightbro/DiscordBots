# Echo Bot — Linux / Raspberry Pi Setup

## 1. First-time setup

```bash
cd ~/DiscordBots/echo-bot
./run.sh
```

This will:
- Install `ffmpeg` via `apt` if missing
- Create a `venv/` virtual environment if missing
- Install/upgrade dependencies from `requirements.txt`
- Check that `.env` exists and has a real `DISCORD_TOKEN`
- Start the bot

If `.env` is missing, create it with:
```
DISCORD_TOKEN=your_token_here
OWNER_ID=your_discord_user_id
```

## 2. Run on startup (systemd)

Edit `echo-bot.service` and adjust:
- `User=pi` — the Linux user the bot should run as
- `WorkingDirectory=` and `ExecStart=` — the absolute path to your `echo-bot/` folder

Then install it:
```bash
sudo cp echo-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable echo-bot
sudo systemctl start echo-bot
```

`enable` makes it start automatically on every boot. `start` runs it now.

### UI alternative (Raspberry Pi Desktop)

You still need to copy the service file once via terminal (Pi Desktop has no GUI for installing systemd units), but you can manage it afterwards with **Tools → Task Manager** → **Services** tab in the taskbar (or open it via the menu: *Preferences → Task Manager*, "Services" tab):
- Find `echo-bot` in the list
- Right-click → Start / Stop / Restart
- There's a checkbox to enable/disable it on boot

This is the GUI equivalent of `systemctl start/stop/restart/enable echo-bot`.

## 3. Logs

Each time the bot starts, it writes fresh log files into `data/logs/`:
- `echo_<timestamp>.log` — full debug log for that run
- `errors_<timestamp>.log` — warnings/errors only for that run

Logs (and cached files in `data/downloads/`) older than 7 days are automatically deleted on every startup.

To follow systemd's view of the bot (stdout/stderr, service start/stop events):
```bash
journalctl -u echo-bot -f
```

To read a specific log file:
```bash
ls data/logs/
tail -f data/logs/echo_<timestamp>.log
```

### UI alternative

Open the **File Manager**, navigate to `~/DiscordBots/echo-bot/data/logs/`, and double-click any `.log` file to open it in the **Text Editor**. Sort by "Modified" date to find the latest run's log.

## 4. Restarting the bot

### Manual restart
```bash
sudo systemctl restart echo-bot
```

### Stop / start
```bash
sudo systemctl stop echo-bot
sudo systemctl start echo-bot
```

### Check status
```bash
systemctl status echo-bot
```

### After internet outages
The bot crashes if Discord's gateway is unreachable. With `Restart=on-failure` and `RestartSec=5` (already set in `echo-bot.service`), systemd retries **forever, every 5 seconds**, with no restart cap — once your internet comes back, it reconnects on its own. No manual action needed.

### UI alternative

Open **Task Manager** (taskbar → *Preferences → Task Manager*) → **Services** tab → right-click `echo-bot` → **Restart** / **Stop** / **Start**. Same effect as the `systemctl` commands above, including checking its current status (running/stopped) at a glance.

## 5. Updating the bot manually

```bash
cd ~/DiscordBots/echo-bot
git pull
source venv/bin/activate
pip install -r requirements.txt
```

`pip install -r requirements.txt` is only strictly needed if `requirements.txt` changed, but it's harmless to run every time.

Then restart the bot:
- **Running via systemd:** `sudo systemctl restart echo-bot`
- **Running manually via `./run.sh`:** stop it (`Ctrl+C` or type `q`) and run `./run.sh` again

## 6. Auto-deploy on git push (GitHub Actions self-hosted runner)

Every push to `main` that touches `echo-bot/` triggers a GitHub Actions workflow that runs directly on the Pi — no polling delay, no cron needed.

### How it works

- GitHub Actions detects the push
- The Pi runner (connected outbound to GitHub — no port forwarding needed) picks up the job
- It pulls the latest code, runs `pip install`, and restarts the bot

### One-time Pi setup

**1. Register the Pi as a self-hosted runner**

Go to your GitHub repo → **Settings → Actions → Runners → New self-hosted runner** → choose **Linux / ARM64**.

GitHub gives you a set of commands to run on the Pi — copy and run them exactly. It installs the runner agent and registers it with your repo.

**2. Start the runner as a service** (so it survives reboots)

After registration, in the runner directory:
```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

**3. Allow systemctl without a password prompt**

The workflow restarts the bot via `sudo systemctl restart echo-bot`. Add a sudoers entry so it doesn't hang waiting for a password:
```bash
sudo visudo
```
Add at the bottom (replace `pi` with your username if different):
```
pi ALL=(ALL) NOPASSWD: /bin/systemctl restart echo-bot
```

That's it — the runner is live. Every push to `main` deploys automatically.

### Checking a deployment

Go to your GitHub repo → **Actions** tab → click the latest workflow run to see live logs for each step (pull, pip install, restart).

### Updating yt-dlp only (no code change)

YouTube breaks yt-dlp frequently. To update just that library without a push:
```bash
cd ~/DiscordBots/echo-bot
source venv/bin/activate
pip install -U yt-dlp
sudo systemctl restart echo-bot
```
