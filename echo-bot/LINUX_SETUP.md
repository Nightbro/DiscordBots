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

Every push to `main` that touches `echo-bot/` triggers a GitHub Actions workflow that runs directly on the Pi — no polling delay, no cron, no public IP needed. The runner connects outbound to GitHub.

---

### Step 1 — Install the runner on the Pi

Open a terminal on the Pi and run these commands exactly:

```bash
mkdir ~/actions-runner && cd ~/actions-runner
curl -o actions-runner-linux-arm64-2.336.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.336.0/actions-runner-linux-arm64-2.336.0.tar.gz
echo "58b758e420b87093fbd4bfddd368074960053e2f1388f01848c82624b90f27d1  actions-runner-linux-arm64-2.336.0.tar.gz" | shasum -a 256 -c
tar xzf ./actions-runner-linux-arm64-2.336.0.tar.gz
```

---

### Step 2 — Configure the runner

Get a fresh registration token from GitHub:
**Repo → Settings → Actions → Runners → New self-hosted runner → Linux / ARM64**
(The token shown there expires in ~1 hour — use it immediately.)

Then run:
```bash
./config.sh --url https://github.com/Nightbro/DiscordBots --token <YOUR_TOKEN_FROM_GITHUB>
```

When prompted:
- **Runner group:** press Enter (default)
- **Runner name:** type `pi` or any name you like
- **Labels:** press Enter (default — keeps the `self-hosted` label the workflow uses)
- **Work folder:** press Enter (default)

---

### Step 3 — Install the runner as a service (survives reboots)

```bash
cd ~/actions-runner
sudo ./svc.sh install
sudo ./svc.sh start
```

Check it's running:
```bash
sudo ./svc.sh status
```

---

### Step 4 — Allow the runner to restart the bot without a password

The deploy workflow runs `sudo systemctl restart echo-bot`. Without this, it hangs waiting for a password that never comes.

```bash
sudo visudo
```

Add this line at the very bottom (replace `pi` with your username if different):
```
pi ALL=(ALL) NOPASSWD: /bin/systemctl restart echo-bot
```

Save and exit (`Ctrl+X` then `Y` if using nano).

---

### That's it — you're live

From now on, every push to `main` that touches `echo-bot/` automatically:
1. Pulls the latest code
2. Runs `pip install -r requirements.txt` and upgrades `yt-dlp`
3. Restarts the bot

### Watching a deployment

Go to **GitHub repo → Actions tab** → click the latest run to see live logs per step.

### Runner management

```bash
# Check runner status
sudo ~/actions-runner/svc.sh status

# Stop the runner
sudo ~/actions-runner/svc.sh stop

# Start the runner
sudo ~/actions-runner/svc.sh start
```

### Updating yt-dlp only (no code change needed)

YouTube breaks yt-dlp frequently. To update just that without pushing a commit:
```bash
cd ~/DiscordBots/echo-bot
source venv/bin/activate
pip install -U yt-dlp
sudo systemctl restart echo-bot
```
