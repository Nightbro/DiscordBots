# Chronicler — Features

The always-current feature list. **This file is enforced, not aspirational:**
`tests/test_help_cog.py` fails the suite if a command exists that this file
does not name, or if this file names a command that no longer exists.

Updating it is mandatory whenever a command is added, removed or renamed.

---

## Status

| Area | State |
|---|---|
| Dice roller | **Shipped** |
| Per-server settings | **Shipped** |
| Channel archive — export | **Shipped** |
| Channel archive — PDF and Word | Planned |
| Channel archive — clearing a channel | Planned |
| Announcements and reminders | Planned |
| Character builder | Planned |
| Session notes | Planned |

---

## Shipped

### Dice roller

Ported from Night Roller, which Chronicler supersedes.

| Command | Feature |
|---|---|
| `!roll` | Roll the server's default die |
| `!roll 5` | Roll a pool of the default die |
| `!roll 2d6+3` | Arbitrary dice notation with modifiers |
| `!roll d20+2d4+1` | Multiple dice groups, added or subtracted |
| `!roll adv +5` | Advantage — two dice, keep the highest |
| `!roll dis +5` | Disadvantage — keep the lowest |
| `!roll 5 (6)` | Score as successes against a difficulty |
| `!roll 2d6+3 sneak attack` | Trailing text becomes a label on the result |

- Two scoring systems per server: **standard** (sum the dice) and **wod**
  (count successes, 1s cancel them, cancelling to zero is a botch).
- Any die size from d2 to d10000; up to 500 dice per group and 25 groups.
- Large rolls degrade to per-group subtotals rather than overflowing the embed.
- Alias: `!r`.

### Per-server settings

| Command | Feature |
|---|---|
| `!config` | Show the server's roll settings |
| `!config show` | The same card |
| `!config system` | Choose `standard` or `wod` scoring |
| `!config die` | Set the default die for pool rolls |
| `!config difficulty` | Set the default success target |
| `!config ones` | Toggle the botch rule |
| `!config reset` | Drop every override |

- Requires **Manage Server**. Alias: `!settings`.
- Values are validated before they are stored; an impossible difficulty for
  the current die is refused with an explanation.
- Switching system moves the die to that system's default, unless the server
  has already chosen one explicitly.

### Channel archive

Exports a channel's history into one zip that opens in a browser.

| Command | Feature |
|---|---|
| `!archive run last <n>` | Export the most recent n messages |
| `!archive run from <id> [to <id>]` | Export between two messages, inclusive |
| `!archive run #channel …` | Export a channel other than the current one |
| `!archive status [#channel]` | What has been exported from this server |
| `!archive` | The same summary |
| `!archive seed <count>` | *(owner)* Post numbered test messages for a safe trial |

- Requires **Manage Server**. The bot needs View Channel and Read Message
  History in the target channel, and Attach Files to deliver the bundle.
- **A range is always required** — there is no default, so an export can never
  guess bounds that a later deletion would act on.
- The bundle holds `index.html`, `style.css`, `manifest.json` listing every
  exported message id, `images/` and `files/`.
- Images and other attachments are stored exactly as uploaded and referenced
  relatively, because Discord's signed attachment links expire after about a
  day — a linked export would be unreadable within 24 hours.
- Non-image attachments are kept as well, so an export followed by a deletion
  cannot silently lose a shared document.
- Always saved on the host under `data/archive/<server id>/`, with the path
  reported; also attached to the reply when it fits the server's upload limit.
- Refuses before downloading anything if the range exceeds 20000 messages or
  1024 MB of attachments. Both are configurable.
- A single unreachable attachment is logged and skipped rather than failing the
  whole export.

### Housekeeping

| Command | Feature |
|---|---|
| `!help` | Paginated command reference, adapts to the server's system |
| `!version` | Running version, derived from git at import time |
| `!ping` | Gateway latency |
| `!restart` | Owner only — exit for systemd to restart |
| `!sync` | Owner only — push slash commands to a guild or globally |

- DM the bot `join`, `invite` or `add` and it replies with the invite URL.
- Alias: `!h` for `!help`. `!restart` and `!sync` are hidden from `!help`.

---

## Planned

Listed here so the roadmap lives beside the feature list. Most carry no
commands yet, by design — see `ARCHITECTURE.md` for the open design questions
each one holds.

### Archive transcripts as PDF and Word

The bundle will also carry `transcript.pdf` and `transcript.docx`, rendered
from the same message model as the HTML rather than converted from it. Messages
only — author, timestamp, text and inline images — with no thread or reply
structure. Word styling comes from an editable template, PDF styling from
`config.yaml`.

Rendering goes through pure-Python libraries on purpose. The obvious choice,
WeasyPrint, needs Pango and cairo as native system libraries, which the Pi
deploy cannot install for itself since it only runs `pip install`.

### Clearing an archived channel

Deleting the messages a completed export saved, as an option on the export
itself rather than a command of its own, so nothing can be deleted that was not
just backed up. The set to delete is read from that bundle's `manifest.json`,
so a missing or unreadable backup refuses outright.

Two Discord constraints shape it: bulk deletion only accepts messages under 14
days old, 100 at a time, and everything older must go one at a time against a
strict rate limit — so clearing a long history is a slow job that reports
progress. Nothing deleted can be recovered, so it will confirm first and a
timeout will delete nothing.

Note that "remove all read messages" is not implementable as such: read state
is per-user and Discord does not expose it to bots at all.

### Chronicle of Darkness dice

A third roll system alongside `standard` and `wod`. Not a variation on the
existing success counting: CofD rerolls 10s (and 9s or 8s with the right
merits), rerolls failures on a rote action, and replaces an empty pool with a
chance die where only a 10 succeeds and a 1 is a dramatic failure. That is
different *rolling*, not different scoring, so it needs its own logic and its
own test file.

### Announcements and reminders

Post to a configured channel, on a schedule, with recurrence for session
night. The only part of Chronicler with no precedent anywhere in this repo:
neither existing bot has a background task or anything persisted with a due
date. Two constraints shape it — every deploy restarts the process, so due
times must survive in JSON and be reconciled on startup rather than held in
memory; and a reminder that came due while the bot was down needs a decided
answer, fire-late or skip.

### Character builder

Chronicle of Darkness sheets, owned per user per server. Storage shape is an
open question. Two things have no precedent here: multi-field entry (every
existing free-text command takes a single consume-rest argument, and no modal
exists anywhere in the repo) and per-guild-per-user records.

### Session notes

Timestamped entries per server, browsable and searchable. The open question is
what a session is — an explicit start/end bracket that notes attach to, or
plain timestamped entries filtered by date.

Both this and the character builder introduce a new category of stored data
for this repo: user-authored free text, attributable to a person, retained
indefinitely. Retention and deletion need deciding alongside the storage, and
the root `PRIVACY_POLICY.md` and `TERMS_OF_SERVICE.md` need updating when they
land.
