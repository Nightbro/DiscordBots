# Night Roller — Architecture

> **Session start rule:** Read this file at the beginning of every session before touching any code in `night-roller/`.

## Overview

Night Roller is a dice bot for a D&D campaign. Its whole job is `!roll` — parse a dice expression, roll it, and print the result. It follows the same conventions as `echo-bot/` (config.yaml → typed constants, `MessageWriter` for every embed, tests for every change), minus everything audio: no voice, no ffmpeg, no downloads, no persisted state.

Both `!` prefix commands and `/` slash commands are supported via discord.py hybrid commands — one definition covers both.

---

## Folder Structure

```
night-roller/
├── bot.py                   # Entry point: logging, bot init, cog loading, error handler
├── config.yaml              # All locality settings (name, prefix, color, emojis, dice limits)
├── .env                     # Secrets only: DISCORD_TOKEN, OWNER_ID, DEV_GUILD_ID
├── .env.example             # Committed template with empty values
├── requirements.txt
├── pytest.ini
├── run.sh / run.bat         # First-run setup + launch (Linux/Pi, Windows)
├── night-roller.service     # systemd unit for the Pi
├── auto_update.sh           # Cron-based fallback updater (poll git, pull, restart)
├── ARCHITECTURE.md          # This file
├── help.md                  # Command reference — update whenever commands change
├── LINUX_SETUP.md           # Discord app setup + Pi deployment + auto-update
│
├── cogs/
│   ├── __init__.py
│   ├── roll.py              # RollCog: !roll — input splitting, advantage handling
│   ├── help.py              # HelpCog: !help — single embed, no pagination
│   └── dev.py               # DevCog: !version, !ping, owner-only !restart
│
├── utils/
│   ├── __init__.py
│   ├── config.py            # Loads config.yaml + .env → typed constants
│   ├── dice.py              # Dice grammar: parse() and roll() — no Discord types
│   └── message.py           # MessageWriter: every embed the bot sends
│
├── data/
│   └── logs/                # Rotating log files (gitignored, .gitkeep only)
│
└── tests/
    ├── conftest.py          # Fixtures: mock_bot, ctx, seeded_rng + sent_embed() helper
    ├── test_config.py
    ├── test_dice.py         # The bulk of the suite — grammar, limits, keep modes
    ├── test_message.py
    ├── test_roll_cog.py
    └── test_help_cog.py
```

---

## Configuration

### `config.yaml` — Locality file

Everything that identifies this bot or tunes its behaviour lives here.

```yaml
bot:
  name: Night Roller
  prefix: "!"
  version: "1.0"
  color: 0x9B59B6
  emojis: { dice: "🎲", crit: "💥", fail: "💀" }

dice:
  default_expression: "d20"   # what a bare !roll rolls
  max_dice: 500               # most dice in one group
  max_sides: 10000            # largest die
  max_groups: 25              # most groups in one expression
  show_rolls: true            # list individual die results in the embed
```

### `.env` — Secrets only

```
DISCORD_TOKEN=      # Bot token from the Discord Developer Portal
OWNER_ID=           # Your Discord user ID — gates !restart
DEV_GUILD_ID=       # Optional: instant slash-command sync to one test server
```

### `utils/config.py`

Loads `.env` and `config.yaml` at import time and exposes typed constants:

```python
BOT_NAME, PREFIX, COLOR, VERSION
EMOJI_DICE, EMOJI_CRIT, EMOJI_FAIL
DEFAULT_EXPRESSION, MAX_DICE, MAX_SIDES, MAX_GROUPS, SHOW_ROLLS
BASE_DIR, DATA_DIR, LOGS_DIR
```

`VERSION` is `<config version>.<git commit count> (<short hash>)` — e.g. `1.0.42 (a1b2c3d)`. This is what makes `!version` a reliable check that an auto-deploy actually landed on the Pi. Paths are created on import if missing; cogs never hardcode `data/` paths.

---

## Core Utils

### `utils/dice.py` — the dice engine

Deliberately free of Discord types so it can be unit-tested directly.

```
expression := term (('+' | '-') term)*
term       := [count] 'd' sides | constant
```

```python
class DiceError(ValueError)            # anything the user can fix by retyping

@dataclass
class DiceGroup:                       # one NdM term
    count, sides, rolls, dropped, negative
    notation -> str                    # "2d6"
    subtotal -> int                    # signed sum of rolls

@dataclass
class RollResult:
    expression, groups, modifier, total, keep
    is_single_d20 -> bool              # crit/fumble applies?
    natural -> int | None              # raw face of a single die
    notation() -> str                  # "2d6 - 1d4", signed
    breakdown() -> str                 # "[4, 6] + 3", dropped dice struck through
    compact_breakdown() -> str         # "2d6(10) + 3", for rolls too big to list

def parse(expression) -> (list[DiceGroup], int)     # validates, does not roll
def roll(expression, *, keep=None, rng=None) -> RollResult
```

- `keep='high'` / `keep='low'` keeps the single best/worst die of the **first** group and drops the rest — this is how advantage and disadvantage are implemented.
- `rng` accepts a seeded `random.Random` so tests are deterministic.
- Parsing is strict: terms after the first must be joined by `+` or `-` (so `1d6d4` is rejected), and every limit from `config.yaml` is enforced in `parse()`.
- **Die sizes are open-ended.** Any `d<sides>` from d2 up to `max_sides` works — `d3`, `d7`, `d37` are as valid as `d20`. The config values are abuse guards, not an allow-list, and any number of groups up to `max_groups` can be chained with `+`/`-`.

### `utils/message.py` — MessageWriter

Centralized embed construction. Cogs never build `discord.Embed` inline.

```python
class MessageWriter:
    @staticmethod def success(title, description='') -> discord.Embed
    @staticmethod def error(title, description='') -> discord.Embed
    @staticmethod def info(title, description='') -> discord.Embed
    @staticmethod def roll_card(result, roller='', *, reason='') -> discord.Embed
```

`roll_card` swaps emoji and color for natural 20 (💥, green) and natural 1 (💀, red), labels advantage/disadvantage in the title, and hides the per-die breakdown when `show_rolls: false`.

**Output degradation.** Discord caps an embed title at 256 characters and a description at 4096, and a wall of numbers stops being readable well before that. `roll_card` therefore collapses in two stages: a title notation over `_MAX_TITLE_NOTATION` (120) becomes "N dice groups", and a breakdown over `_MAX_BREAKDOWN` (600, roughly 150 dice) falls back to `compact_breakdown()`, then to nothing at all. The total is always shown. This is what makes raising the `config.yaml` limits safe.

---

## Cogs

### `cogs/roll.py` — RollCog

| Command | Aliases | Description |
|---|---|---|
| `!roll [expression] [label]` | `!r` | Roll dice; bare `!roll` uses `default_expression` |

Two module-level helpers do the input handling and are tested independently of Discord:

- `split_input(text) -> (keep, expression, reason)` — strips a leading `adv`/`dis` word, greedily consumes dice-looking tokens into the expression (so `2d6 + 3` works with spaces), and treats the remainder as a free-text label.
- `advantage_expression(expr) -> str` — doubles the first dice group so `keep` has two dice to choose from; a bare modifier (or nothing) becomes `2d20`.

`DiceError` is caught and rendered via `MessageWriter.error` — the bot never raises at the user.

### `cogs/help.py` — HelpCog

`!help` (alias `!h`) — one `MessageWriter.info` embed built from a format string using `PREFIX` and `DEFAULT_EXPRESSION`, so changing the prefix in `config.yaml` updates the help text too.

### `cogs/dev.py` — DevCog

| Command | Description |
|---|---|
| `!version` | Running version — use it to confirm a deploy landed |
| `!ping` | Gateway latency |
| `!restart` | Owner only (`OWNER_ID`) — closes the bot so systemd restarts it |

---

## Entry Point (`bot.py`)

- Patches `ssl.create_default_context` to use `certifi` first (Windows cert issues), before any other import
- Per-run rotating log file at `data/logs/night_roller_<timestamp>.log` (2 MB, 3 backups) plus an INFO console handler
- Intents: defaults + `message_content` (required for `!` prefix commands). **No voice intent** — this bot never joins voice
- Loads cogs in order: `roll`, `help`, `dev`
- On `on_ready`: syncs the slash tree to `DEV_GUILD_ID` if set (instant, vs. up to an hour for a global sync)
- On `on_command_error`: ignores `CommandNotFound`, reports permission failures, logs everything else with a traceback

---

## Deployment

Runs on the same Raspberry Pi as echo-bot, as its own systemd service (`night-roller.service`). Pushes to `main` that touch `night-roller/**` trigger `.github/workflows/deploy-night-roller.yml` on the self-hosted runner, which pulls, pip-installs, and restarts the service. `auto_update.sh` is the cron fallback if the runner is down. See `LINUX_SETUP.md`.

---

## Rules for Working on night-roller

- Help: update `night-roller/help.md` whenever commands are added, removed, or renamed
- Tests: every change needs a corresponding test in `night-roller/tests/`; run `pytest` from `night-roller/` before committing
- Architecture: update this file when structure changes
- Paths: always derive from `utils/config.py` constants — never hardcode `data/` paths in cogs
- Embeds: always use `MessageWriter` — never build `discord.Embed` inline in cogs
- Dice logic: keep it in `utils/dice.py`, free of Discord types — cogs only parse input and present results
