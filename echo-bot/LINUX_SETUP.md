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

## 6. Auto-update on git push (cron poller)

`auto_update.sh` polls GitHub every few minutes and automatically pulls, reinstalls deps, and restarts the bot when new commits are found.

### First-time setup

Make it executable:
```bash
chmod +x ~/DiscordBots/echo-bot/auto_update.sh
```

Allow the script to restart the bot without a password prompt (required for cron, which has no sudo session):
```bash
sudo visudo
```
Add this line at the bottom (replace `pi` with your username if different):
```
pi ALL=(ALL) NOPASSWD: /bin/systemctl restart echo-bot
```
Save and exit (`Ctrl+X` then `Y` in nano).

### Set up the cron job

```bash
crontab -e
```
Add this line to poll every 5 minutes:
```
*/5 * * * * /home/pi/DiscordBots/echo-bot/auto_update.sh >> /home/pi/DiscordBots/echo-bot/data/logs/auto_update.log 2>&1
```
Replace `/home/pi` with your actual home path if different.

Save and exit. The cron job starts immediately — no reboot needed.

### How it works

- Every 5 minutes cron runs `auto_update.sh`
- It does a `git fetch` and compares local vs remote commit hashes
- If they match → exits silently (nothing logged)
- If they differ → pulls, reinstalls deps, restarts the bot, and logs the update with a timestamp

### Check the auto-update log

```bash
tail -f ~/DiscordBots/echo-bot/data/logs/auto_update.log
```

### Updating yt-dlp only (no code change)

YouTube breaks yt-dlp frequently. To update just that library without waiting for a push:
```bash
cd ~/DiscordBots/echo-bot
source venv/bin/activate
pip install -U yt-dlp
sudo systemctl restart echo-bot
```
