# Night Roller — Architecture

> **Session start rule:** Read this file at the beginning of every session before touching any code in `night-roller/`.

## Overview

Night Roller is a dice bot for tabletop campaigns. Its whole job is `!roll` — parse a dice expression, roll it, and print the result — in one of two scoring systems, chosen per server: **standard** (sum the dice) or **wod** (count successes against a difficulty, World of Darkness style). It follows the same conventions as `echo-bot/` (config.yaml → typed constants, `MessageWriter` for every embed, tests for every change), minus everything audio: no voice, no ffmpeg, no downloads, no persisted state.

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
│   ├── roll.py              # RollCog: !roll — input splitting, pools, advantage
│   ├── settings.py          # SettingsCog: !config — per-guild system/die/difficulty
│   ├── help.py              # HelpCog: !help — single embed, adapts to the guild system
│   ├── invite.py            # InviteCog: DM "join" -> invite URL (on_message listener)
│   └── dev.py               # DevCog: !version, !ping, owner-only !restart
│
├── utils/
│   ├── __init__.py
│   ├── config.py            # Loads config.yaml + .env → typed constants
│   ├── persistence.py       # BaseConfig: JSON load/save; GuildConfig subclass
│   ├── guild_config.py      # Per-guild settings + validated setters
│   ├── dice.py              # Dice grammar: parse() and roll() — no Discord types
│   └── message.py           # MessageWriter: every embed the bot sends
│
├── data/
│   ├── guild_config.json    # Per-guild settings (gitignored)
│   └── logs/                # Rotating log files (gitignored, .gitkeep only)
│
└── tests/
    ├── conftest.py          # Fixtures: mock_bot, ctx, seeded_rng + sent_embed() helper
    ├── test_config.py
    ├── test_dice.py         # The bulk of the suite — grammar, limits, keep modes
    ├── test_successes.py    # Hit counting, the botch rule, outcomes
    ├── test_guild_config.py
    ├── test_message.py
    ├── test_roll_cog.py
    ├── test_settings_cog.py
    ├── test_invite_cog.py
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
  invite_url: "https://discord.com/oauth2/authorize?..."   # sent on a "join" DM
  emojis: { dice: "🎲", crit: "💥", fail: "💀" }

dice:
  default_system: standard    # standard | wod — overridable per guild
  default_die: 20             # bare "!roll" = 1d20, "!roll 5" = 5d20
  default_difficulty: 6       # success target when counting hits
  default_subtract_ones: true # WoD botch rule
  max_dice: 500               # most dice in one group
  max_sides: 10000            # largest die
  max_groups: 25              # most groups in one expression
  show_rolls: true            # list individual die results in the embed
```

The four `default_*` dice values are **defaults, not fixed settings** — each guild overrides them through `!config`, stored in `data/guild_config.json`.

### `.env` — Secrets only

```
DISCORD_TOKEN=      # Bot token from the Discord Developer Portal
OWNER_ID=           # Your Discord user ID — gates !restart
DEV_GUILD_ID=       # Optional: instant slash-command sync to one test server
```

### `utils/config.py`

Loads `.env` and `config.yaml` at import time and exposes typed constants:

```python
BOT_NAME, PREFIX, COLOR, VERSION, INVITE_URL
DEFAULT_SYSTEM, DEFAULT_DIE, DEFAULT_DIFFICULTY, DEFAULT_SUBTRACT_ONES
EMOJI_DICE, EMOJI_CRIT, EMOJI_FAIL
DEFAULT_EXPRESSION, MAX_DICE, MAX_SIDES, MAX_GROUPS, SHOW_ROLLS
BASE_DIR, DATA_DIR, LOGS_DIR, GUILD_CONFIG_FILE
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
def roll(expression, *, keep=None, target=None, subtract_ones=False, rng=None) -> RollResult
```

**Success counting.** Passing `target` switches the result from a sum to a pool score, and `RollResult` grows a second set of properties:

```python
counts_successes -> bool     # target was given
faces -> list[int]           # every kept die (dropped dice excluded)
hits -> int                  # faces >= target
ones -> int                  # faces == 1, only when subtract_ones
net_hits -> int              # hits - ones; can go negative
outcome -> str               # 'success' | 'failure' | 'botch'
```

**Outcome rule** (Storyteller as this table plays it): a success survives → `success`; otherwise any 1 on the table → `botch`, *including successes cancelled exactly to zero*; nothing hit and no 1s → `failure`. With `subtract_ones` off, `ones` is always 0, so a botch is impossible by construction.

`total` is still computed, so nothing about sum mode changes — the embed simply reads `net_hits` instead when `counts_successes` is true. `breakdown()` marks hits in bold and cancelling 1s with underline.

- `keep='high'` / `keep='low'` keeps the single best/worst die of the **first** group and drops the rest — this is how advantage and disadvantage are implemented.
- `rng` accepts a seeded `random.Random` so tests are deterministic.
- Parsing is strict: terms after the first must be joined by `+` or `-` (so `1d6d4` is rejected), and every limit from `config.yaml` is enforced in `parse()`.
- **Die sizes are open-ended.** Any `d<sides>` from d2 up to `max_sides` works — `d3`, `d7`, `d37` are as valid as `d20`. The config values are abuse guards, not an allow-list, and any number of groups up to `max_groups` can be chained with `+`/`-`.

### `utils/persistence.py` + `utils/guild_config.py` — per-guild settings

`BaseConfig` is the JSON load/save/get/set/delete base (mirroring echo-bot's); `GuildConfig` binds it to `GUILD_CONFIG_FILE`. A corrupt or unreadable file returns `{}` rather than raising — bad JSON must never take the bot down mid-session.

`guild_config.py` layers the settings model on top:

```python
SYSTEM_STANDARD = 'standard'; SYSTEM_WOD = 'wod'

get_system/get_die/get_difficulty/get_subtract_ones(guild_id)   # typed reads
is_wod(guild_id) -> bool
get_all_settings(guild_id) -> dict          # overrides merged over defaults
set_system/set_die/set_difficulty/set_subtract_ones(...)        # validated
reset_guild(guild_id)
```

- Reads fall back to the `config.yaml` global default per key, so a guild row only ever holds what it actually changed, and **guild_id 0 (a DM) transparently gets the defaults**.
- Setters raise `SettingError` with a user-facing message; the cog renders it via `MessageWriter.error`. Notably `set_difficulty` rejects a target above the current die — difficulty 11 on a d10 can never succeed, so it is caught at config time rather than producing silently impossible rolls.
- `set_system('wod')` also moves the die to d10, *unless* the guild already set a die explicitly.

### `utils/message.py` — MessageWriter

Centralized embed construction. Cogs never build `discord.Embed` inline.

```python
class MessageWriter:
    @staticmethod def success(title, description='') -> discord.Embed
    @staticmethod def error(title, description='') -> discord.Embed
    @staticmethod def info(title, description='') -> discord.Embed
    @staticmethod def roll_card(result, roller='', *, reason='') -> discord.Embed
    @staticmethod def config_card(settings, prefix='!') -> discord.Embed
    @staticmethod def invite() -> discord.Embed
```

`roll_card` swaps emoji and color for natural 20 (💥, green) and natural 1 (💀, red), labels advantage/disadvantage in the title, and hides the per-die breakdown when `show_rolls: false`.

**Output degradation.** Discord caps an embed title at 256 characters and a description at 4096, and a wall of numbers stops being readable well before that. `roll_card` therefore collapses in two stages: a title notation over `_MAX_TITLE_NOTATION` (120) becomes "N dice groups", and a breakdown over `_MAX_BREAKDOWN` (600, roughly 150 dice) falls back to `compact_breakdown()`, then to nothing at all. The total is always shown. This is what makes raising the `config.yaml` limits safe.

---

## Cogs

### `cogs/roll.py` — RollCog

| Command | Aliases | Description |
|---|---|---|
| `!roll [expression] [(target)] [label]` | `!r` | Roll dice; a bare count uses the guild's die |

Module-level helpers do the input handling and are tested independently of Discord:

- `split_input(text) -> (keep, expression, target, reason)` — pulls `(n)` out from anywhere in the input, strips a leading `adv`/`dis` word, greedily consumes dice-looking tokens into the expression (so `2d6 + 3` works with spaces), and treats the remainder as a free-text label.
- `is_bare_pool(expr) -> bool` / `resolve_expression(expr, die) -> str` — a dice-less count like `5` means "five of this guild's default die", so `5` becomes `5d10` in a WoD server and `5d20` in a standard one. Empty input becomes `1d<die>`.
- `advantage_expression(expr) -> str` — doubles the first dice group so `keep` has two dice to choose from; a bare modifier (or nothing) becomes `2d20`.

**When success counting kicks in** — the rule that keeps old behaviour intact:

| Input | Standard guild | WoD guild |
|---|---|---|
| `!roll 5` | `5d20`, summed | `5d10` vs the guild difficulty, 1s cancel |
| `!roll 5 (5)` | `5d20`, hits vs 5 | `5d10` vs 5, 1s cancel |
| `!roll 2d6+3d8` | summed | **summed** — explicit notation is never rescored |

An explicit `(n)` always counts hits, in any system. The automatic difficulty applies only to a *bare pool* in a WoD guild, which is what stops `2d6+3d8` from silently changing meaning for a campaign that switched systems. `subtract_ones` is a WoD-only rule and is never applied in a standard guild.

`DiceError` is caught and rendered via `MessageWriter.error` — the bot never raises at the user.

### `cogs/settings.py` — SettingsCog

`!config` (alias `!settings`) — a hybrid group, every subcommand gated by `has_guild_permissions(manage_guild=True)`, with `cog_check` refusing DMs since the settings are server-scoped.

| Subcommand | Effect |
|---|---|
| `!config` / `!config show` | Print the effective settings |
| `!config system <standard\|wod>` | Switch scoring system |
| `!config die <sides>` | Default die for pool rolls |
| `!config difficulty <n>` | Default success target |
| `!config ones <on\|off>` | Toggle the botch rule |
| `!config reset` | Delete the guild's overrides |

Every successful change re-renders the settings card, so the user always sees the resulting state rather than a bare "ok".

### `cogs/help.py` — HelpCog

`!help` (alias `!h`) — one `MessageWriter.info` embed. The body is a format string filled from `PREFIX` **and the calling guild's settings**, so a WoD server sees `1d10`, its own difficulty, and a note about the botch rule, while a standard server sees `1d20` and how to switch.

### `cogs/invite.py` — InviteCog

An `on_message` listener, not a command — it answers a plain `join` DM (no prefix needed) with `MessageWriter.invite()`.

- **DMs only.** It returns immediately when `message.guild is not None`; in a server the bot is obviously already added.
- `is_invite_request(content)` is a module-level pure function (strip → lowercase → drop a leading prefix → match `join` / `invite` / `add`), so the matching is tested without constructing Discord objects.
- Cog listeners are additive — this one does not override `bot.on_message`, so command processing is untouched and `!roll` still works inside DMs.

The URL lives in `config.yaml` as `invite_url`; regenerate it in the Developer Portal (OAuth2 → URL Generator) if the requested permissions ever change.

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
- Loads cogs in order: `roll`, `settings`, `help`, `invite`, `dev`
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
- Guild settings: read through `utils/guild_config.py` accessors, never by touching `guild_config.json` directly; `guild_id` 0 means "no guild" (a DM) and must always resolve to the defaults
- Tests must never write to the real `data/` — the autouse `isolated_guild_config` fixture in `conftest.py` repoints the store at `tmp_path`
