# Chronicler — Command Reference

Chronicler keeps the table. Dice work today; announcements, the character
builder and session notes are on the way (see `FEATURES.md`).

Every command below works both as a `!` prefix command and as a `/` slash
command — one definition serves both.

---

## Rolling

| Command | What it does |
|---|---|
| `!roll` | Roll one of this server's default die |
| `!roll 5` | Roll 5 of the default die |
| `!roll 2d6+3` | Any number of dice, plus or minus a modifier |
| `!roll d20+2d4+1` | Combine several dice groups |
| `!roll adv +5` | Advantage — rolls two d20, keeps the highest |
| `!roll dis +5` | Disadvantage — keeps the lowest |
| `!roll 2d6+3 sneak attack` | Anything after the dice is shown as a label |

Alias: `!r`.

### Expression syntax

- **Any die size works** — `d3`, `d7`, `d37`, `d100`. The standard set is not
  special; the limits below are abuse guards, not an allow-list.
- **Any number of dice groups**, added or subtracted: `4d6+2d10-1d4+5`.
- Whitespace and case are ignored, so `2D6 + 3` is the same as `2d6+3`.

### Limits

| Limit | Value |
|---|---|
| Dice in one group | 500 |
| Largest die | d10000 |
| Dice groups in one expression | 25 |

A roll too large to print die by die collapses to per-group subtotals, e.g.
`300d20(3193)`.

---

## Counting successes (dice pools)

Add a difficulty in parentheses to score a roll as successes instead of a sum.

| Command | What it does |
|---|---|
| `!roll 5 (6)` | Roll 5 dice, count how many are 6 or higher |
| `!roll 6d10 (7)` | The same, with explicit dice |

### World of Darkness servers

Set with `!config system wod`:

- A plain pool roll is scored against the server difficulty automatically —
  no parentheses needed.
- Each `1` cancels one success. Turn that off with `!config ones off`.
- Successes cancelled to exactly zero with a `1` on the table is a **botch**,
  not a plain failure.
- Switching to `wod` moves the default die to d10 unless the server has
  already set a die of its own.
- Explicit expressions like `!roll 2d6+3d8` keep summing, even here.

```
!roll 5          → 5d10 at difficulty 6, 1s cancel
!roll 5 (5)      → 5d10 at difficulty 5
!roll 2d6+3d8    → summed, unchanged
```

**Chronicle of Darkness is not supported yet.** Its 10-again cascades, rote
rerolls and chance die change how dice are rolled rather than how they are
scored, so it needs its own system rather than another difficulty number.

---

## Channel archive

Exports a channel's history into a single zip you can open in a browser. Needs
the **Manage Server** permission.

| Command | What it does |
|---|---|
| `!archive run last 500` | Export the most recent 500 messages |
| `!archive run from <message_id>` | Export from that message onwards |
| `!archive run from <id> to <id>` | Export between two messages, inclusive |
| `!archive run #other last 200` | Export a channel other than this one |
| `!archive status` | What has been exported from this server |
| `!archive status #channel` | Narrow that to one channel |
| `!archive` | The same summary |
| `!archive seed <count>` | *(owner)* Post numbered test messages |

### The range is always required

There is no default range, deliberately. An export that guesses its own bounds
is one that could later delete the wrong messages.

Message ids come from right-clicking a message and choosing **Copy Message ID**
(Discord needs Developer Mode enabled under Settings → Advanced).

### What the bundle contains

```
index.html       open this
style.css        edit it if you want it to look different
transcript.pdf   the same messages as a PDF
transcript.docx  the same messages as a Word document
manifest.json    every exported message id, the range, who ran it
images/          image attachments, exactly as uploaded
files/           every other attachment, exactly as uploaded
```

The PDF and Word versions carry the messages — author, timestamp, text and
inline images — and nothing else. No threads, replies or embeds. Images in them
are downscaled to print resolution; the untouched originals stay in `images/`.

To restyle the Word output, put a `.docx` with your own **Title**, **Subtitle**,
**Heading 2** and **Normal** styles into `assets/` and name it in
`archive.docx_template`. Only its styles are used, never its text.

If the PDF shows `?` instead of Cyrillic or other non-Latin characters, no
system TrueType font was found. Point `archive.pdf_font` at one.

Images are **saved into the bundle**, not linked back to Discord — Discord's
attachment links are signed and stop working after about a day, so a linked
export would rot.

Non-image attachments are kept too. Exporting only images would quietly lose
anything else that had been shared.

### Where it ends up

Always written to the host machine under `data/archive/<server id>/`, and the
bot tells you the full path. If the zip is small enough for the server's upload
limit it is attached to the reply as well; a large one is not, because Discord
would reject it.

### Limits

| Limit | Default |
|---|---|
| Messages in one export | 20000 |
| Attachment bytes in one export | 1024 MB |

Both are refused before anything is downloaded. Export a smaller range instead.

### Clearing a channel

Not built yet. When it arrives it will delete only the messages a completed
export actually saved, verified against that bundle's `manifest.json`, so
nothing can be removed that is not already backed up.

---

## Server settings

These need the **Manage Server** permission. Alias: `!settings`.

| Command | What it does |
|---|---|
| `!config` | Show this server's roll settings |
| `!config show` | The same card |
| `!config system <standard\|wod>` | How rolls are scored |
| `!config die <sides>` | Default die for pool rolls |
| `!config difficulty <n>` | Default success target |
| `!config ones <on\|off>` | Whether each 1 cancels a success |
| `!config reset` | Drop every override, back to global defaults |

`!config die` also accepts `!config dice`, and `!config difficulty` accepts
`!config diff`. On/off settings accept `on/true/yes/enable/1` and
`off/false/no/disable/0`.

A difficulty higher than the current die is refused — it could never succeed.

---

## Direct messages

DM the bot the word `join` (or `invite`, or `add`) and it replies with the
invite URL. Until the Discord application exists, it says so instead.

---

## Other

| Command | What it does |
|---|---|
| `!help` | Paginated command reference — `!help rolling`, `!help settings` |
| `!version` | Running version, as `base.commits (hash)` |
| `!ping` | Gateway latency |
| `!restart` | Owner only — exit so systemd restarts the process |
| `!sync` | Owner only — push slash commands to a guild, or globally |

Alias: `!h` for `!help`. `!restart` and `!sync` are hidden from `!help`.
