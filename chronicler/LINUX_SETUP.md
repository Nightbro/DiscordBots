# Chronicler — Setup and Deployment

Keep this file current. Whenever a feature needs a new Discord permission or a
new piece of configuration, it is recorded here in the same change.

> **Status:** the application has not been created yet. Sections 1 and 2 are the
> steps to do that, written out exactly; nothing below has been walked through
> on a live application.

---

## 1. Creating the Discord application

Only you can do this — it needs your Discord login, and the token must never be
pasted anywhere but `.env` on the machine that runs the bot.

**1.1** Go to the [Developer Portal](https://discord.com/developers/applications)
and click **New Application**. Name it `Chronicler`.

**1.2** On **General Information**, copy the **Application ID**. That is the
`client_id` the invite URL needs. Keep the tab open.

**1.3** Open the **Bot** tab. Set the username and avatar if you want them
different from the application name.

**1.4** Still on **Bot**, under **Privileged Gateway Intents**, turn on
**Message Content Intent**. Leave Server Members and Presence off — Chronicler
uses neither. Save.

Without Message Content the bot connects but sees empty message bodies, so `!`
commands silently do nothing and exports come out blank.

**1.5** Check two switches on the same page:

| Switch | Set it to | Why |
|---|---|---|
| **Public Bot** | **Off** | Only you can add it to servers. Turn it on only if you want strangers inviting it |
| **Requires OAuth2 Code Grant** | **Off** | If this is on, the invite link fails with a confusing error. It is the most common setup mistake |

**1.6** Click **Reset Token**, then **Copy**. Discord shows it once and never
again — if you lose it, reset it again. Paste it straight into `.env` on the
machine that will run the bot (section 3). Do not commit it, paste it into a
chat, or send it to anybody, including me.

**1.7** Generate the invite URL — section 2.

---

## 2. Permissions the bot needs

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
| Manage Messages | Clearing a channel with `!archive run … --purge` |

Chronicler needs no voice permissions. It never joins a voice channel.

**Manage Messages is optional.** Everything except `--purge` works without it,
and an export refuses up front if you ask to purge while it is missing. If you
never intend to clear channels, leave it off — there is no reason to grant a
deletion permission you do not want used. Both the bot *and* whoever runs the
command need it.

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

### The invite URL

Go to **OAuth2 → URL Generator**, tick `bot` and `applications.commands`, then
tick the permissions from the table above. Discord builds the URL at the bottom
of the page; that is the one to use.

To check what it produced, or to skip the clicking, these are the same URLs with
the permission numbers already worked out. Replace `YOUR_APPLICATION_ID` with
the ID from step 1.2:

**With** Manage Messages — exports and channel clearing:

```
https://discord.com/oauth2/authorize?client_id=YOUR_APPLICATION_ID&permissions=125952&integration_type=0&scope=bot+applications.commands
```

**Without** Manage Messages — exports only, no deletion possible:

```
https://discord.com/oauth2/authorize?client_id=YOUR_APPLICATION_ID&permissions=117760&integration_type=0&scope=bot+applications.commands
```

If the generator gives you a different number, it has included something extra.
Compare the ticked boxes against the table rather than trusting the number — and
for reference, `night-roller` currently requests `2815284491020352`, which grants
it thread management, pinning and `mention_everyone` that it has never used.
Chronicler deliberately asks for six permissions and no more.

Paste the finished URL into `invite_url` in `config.yaml` and commit that. Until
it is set, DMing the bot `join` replies that there is no link yet rather than
sending a broken one. The URL contains no secret — only the token does.

Open the URL, pick the server, and confirm. You need **Manage Server** on that
server to add a bot to it.

---

## 3. Configuration

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
| `pdf_image_width_mm` | 120 | Width of inline images in the PDF and Word files |
| `pdf_font_size` | 10 | Body text size in the PDF |
| `pdf_font` | *(empty)* | A `.ttf` for the PDF. Empty auto-detects a system font; see below |
| `docx_template` | *(empty)* | A `.docx` whose styles the Word transcript borrows |
| `retention_days` | 0 | **0 means bundles are never auto-deleted** |
| `confirm_secs` | 60 | How long a deletion confirmation stays live |
| `progress_every` | 250 | Edit the progress message every N messages |

`retention_days` defaults to off on purpose. A bundle can be the only remaining
copy of a cleared channel, so deleting backups by age has to be a choice
somebody makes deliberately.

### Fonts for the PDF

The PDF needs a TrueType font to render anything outside Latin-1 — Cyrillic,
Greek, Turkish and so on. Chronicler looks for one automatically:

| Platform | Looked for |
|---|---|
| Debian / Raspberry Pi OS | `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`, then Liberation |
| Windows | `C:/Windows/Fonts/segoeui.ttf`, then `arial.ttf` |

Raspberry Pi OS ships DejaVu in the `fonts-dejavu-core` package, which is
normally already installed. If it is not:

```bash
sudo apt install fonts-dejavu-core
```

With no font found the export still succeeds — the PDF falls back to a Latin-1
font, replaces characters it cannot encode with `?`, and logs a warning. The
HTML and Word versions are unaffected either way, since neither has that
limitation.

To use a specific font, drop it in `assets/` and set `archive.pdf_font` to its
filename, or give an absolute path.

### Styling the Word transcript

Leave `archive.docx_template` empty for Word's own defaults. To restyle it,
create a `.docx` in Word, set up the **Title**, **Subtitle**, **Heading 2** and
**Normal** styles how you want them, save it into `assets/`, and name it in
`archive.docx_template`.

Only the template's *styles* are used. Any text in it is stripped, so a template
cannot leak placeholder content into an export.

---

## 4. Running it

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

## 5. Deploying to the Raspberry Pi

Assumes the repo at `/home/pi/DiscordBots` and the other bots already running.
For any other machine, see section 6 instead.

**Check the Pi's Python first.** Chronicler needs 3.11+, where Echo and Night
Roller do not, so a Pi that happily runs those two may still refuse this one:

```bash
python3 --version
```

Bookworm ships 3.11 and is fine. Bullseye ships 3.9 and is not — `pip install`
will stop with "no matching distribution found for fpdf2". See section 6.2 for
what to do about that.

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

Use one or the other. Both together means a push triggers the runner while cron
also notices the new commit, and the bot restarts twice.

---

## 6. Deploying to a different server

Nothing here is Pi-specific except hardcoded paths and a username. Three files
assume `pi` and `/home/pi/DiscordBots`, and all three need editing for another
machine.

### 6.1 What to change

| File | Line | Change it to |
|---|---|---|
| `chronicler.service` | `User=pi` | the account that will run the bot |
| `chronicler.service` | `WorkingDirectory=` | where the repo is checked out |
| `chronicler.service` | `ExecStart=` | the same path, plus `/venv/bin/python bot.py` |
| `chronicler.service` | `EnvironmentFile=` | the same path, plus `/.env` |
| `auto_update.sh` | `sudo systemctl restart chronicler` | only if you rename the service |
| `.github/workflows/deploy-chronicler.yml` | `~/DiscordBots` | the checkout path on that machine |

The unit file is committed as the Pi's version. If the new machine is permanent,
copy it to something like `chronicler-vps.service` rather than editing the
committed one, so the two deployments do not fight over the same file.

### 6.2 Requirements on the host

| Needs | Why |
|---|---|
| **Python 3.11 or newer** | `fpdf2` and `Pillow` both require it — see below |
| `python3-venv` | `run.sh` builds a virtualenv |
| `git` | The updater pulls |
| systemd | Only for the service; `./run.sh` works without it |
| `fonts-dejavu-core` | Optional — only so PDF exports render non-Latin text |

No `apt` packages are needed for the Python dependencies themselves. Every one
is a pure-Python wheel, which is exactly why `fpdf2` was chosen over WeasyPrint.

**Check the interpreter before anything else:**

```bash
python3 --version
```

Chronicler needs **3.11+**, which is a higher bar than Echo or Night Roller —
both of those run on anything from 3.8. The floor comes from `fpdf2` and
`Pillow`, not from the code. Raspberry Pi OS **Bookworm** ships Python 3.11;
**Bullseye** ships 3.9 and will not do.

`requirements.txt` pins minimum versions on purpose, so a too-old interpreter
fails at install with a plain "no matching distribution" rather than quietly
installing ancient releases that lack the APIs used here.

If the host is stuck on an older Python, the options are: upgrade the OS,
install a newer Python alongside (`pyenv`, or deadsnakes on Ubuntu) and point
`run.sh` at it, or run Chronicler somewhere else. There is no version of this
that works on 3.9.

### 6.3 Steps

```bash
git clone https://github.com/Nightbro/DiscordBots.git
cd DiscordBots/chronicler
cp .env.example .env && nano .env        # paste the token
./run.sh                                 # builds the venv, installs, starts
```

If it starts cleanly, stop it and install the service with your edited unit:

```bash
sudo cp chronicler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now chronicler
systemctl status chronicler
```

### 6.4 Keeping it updated

Pick one of three, in descending order of effort:

**A self-hosted Actions runner**, like the Pi has. Best if you push often.
Register it from the repository's **Settings → Actions → Runners**, then add a
second workflow pointing at that machine's path. The existing workflow targets
whichever runner picks the job up, so **two runners on one repository will
fight** over it — give the new one a label and filter on it with
`runs-on: [self-hosted, your-label]`.

**Cron**, with `auto_update.sh`. No GitHub configuration at all, updates within
the polling interval. This is the better choice for a machine you do not control
the repository settings of.

**By hand**, when you deploy rarely:

```bash
cd /path/to/DiscordBots && git pull
cd chronicler && source venv/bin/activate && pip install -q -r requirements.txt
sudo systemctl restart chronicler
```

### 6.5 Two things that bite

**The bot token is per application, not per machine.** Running the same token in
two places at once makes Discord disconnect both in a loop. To move the bot,
stop it on the old machine *first*. To run a second instance deliberately — a
staging copy — create a second application with its own token.

**`data/` does not travel with git.** It is gitignored, so a new machine starts
with no per-server settings and no export bundles. Copy `data/` across manually
if you want to keep them:

```bash
rsync -av /home/pi/DiscordBots/chronicler/data/ newhost:/path/DiscordBots/chronicler/data/
```

Export bundles are the only copy of anything that has been purged from a
channel, so move them before decommissioning a machine.

---

## 7. Note on Night Roller

Chronicler supersedes Night Roller and answers the same `!roll`. Do not add both
to one server — they will both reply. Night Roller keeps running until
Chronicler is deployed and verified, then it gets retired.

---

## 8. Troubleshooting

| Symptom | Cause |
|---|---|
| `no matching distribution found for fpdf2` | Python older than 3.11 — see section 6.2 |
| The invite link errors instead of asking which server | **Requires OAuth2 Code Grant** is on; turn it off (step 1.5) |
| Bot is online but `!` commands do nothing | **Message Content Intent** is off (step 1.4) |
| Exports come out with empty message bodies | Same — Message Content Intent |
| Bot connects and disconnects in a loop | The same token is running somewhere else too; stop one of them |
| `DISCORD_TOKEN not set in .env` | No `.env`, or the variable is empty |
| Slash commands missing | No `DEV_GUILD_ID`; wait, or run `!sync` |
| `!version` shows an old hash | The restart did not take — check `systemctl status` |
| Export says it needs View Channel | The bot is not in that channel's overwrites |
| Export says it needs Read Message History | Missing from the invite, or denied per-channel |
| Bundle not attached to the reply | Larger than the server's upload limit; collect it from the reported path |
| `!archive seed` does nothing | Owner-only — `OWNER_ID` must match your user id |
| `--purge` refused before exporting | Manage Messages missing, from the bot or from you |
| A purge left messages behind | Reported as partly cleared; the log says which failed and why |
| Clearing an old channel is very slow | Messages over 14 days old delete one at a time; this is a Discord limit |
