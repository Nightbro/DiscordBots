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
