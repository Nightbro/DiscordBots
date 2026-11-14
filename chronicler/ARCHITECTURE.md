# Chronicler — Architecture

> **Session start rule:** Read this file at the beginning of every session
> before touching any code in `chronicler/`.

## Overview

Chronicler keeps a tabletop chronicle. Four responsibilities, of which one is
built: **dice** (shipped), **announcements and reminders**, a **character
builder**, and **session notes**. The target system is Chronicle of Darkness.

It is the third bot in this repo and follows the same conventions as
`echo-bot/` and `night-roller/`: `config.yaml` → typed constants, all runtime
paths derived from `utils/config.py`, every embed built by `MessageWriter`,
domain logic in `utils/` free of Discord types, a test for every change.

Chronicler **absorbs Night Roller**. The dice engine and its tests were ported
across. Night Roller stays in the repo and keeps running until Chronicler
ships, then gets retired — until that point the two must not be deployed to
the same server, since both answer `!roll`.

Both `!` prefix commands and `/` slash commands are supported via discord.py
hybrid commands — one definition covers both.

---

## Folder Structure

```
chronicler/
├── bot.py                   # Entry point: SSL patch, logging, cog loading, error handler
├── config.yaml              # All locality: name, prefix, color, emojis, dice limits
├── .env                     # Secrets only: DISCORD_TOKEN, OWNER_ID, DEV_GUILD_ID
├── .env.example             # Committed template with empty values
├── requirements.txt
├── pytest.ini
├── run.sh / run.bat         # First-run setup + launch (Linux/Pi, Windows)
├── chronicler.service       # systemd unit for the Pi
├── auto_update.sh           # Cron-based fallback updater (poll git, pull, restart)
├── ARCHITECTURE.md          # This file
├── FEATURES.md              # Feature list — enforced by tests, update it
├── help.md                  # Command reference — enforced by tests, update it
├── LINUX_SETUP.md           # Discord app setup + deployment
│
├── cogs/                    # Thin: parse input, present results
│   ├── __init__.py
│   ├── roll.py              # RollCog: !roll — input splitting, pools, advantage
│   ├── settings.py          # SettingsCog: !config — per-guild system/die/difficulty
│   ├── help.py              # HelpCog: !help — paginated pages, adapts to the system
│   ├── invite.py            # InviteCog: DM "join" -> invite URL (on_message listener)
│   └── dev.py               # DevCog: !version, !ping, owner-only !restart / !sync
│
├── utils/                   # Domain logic — no Discord types outside message.py
│   ├── __init__.py
│   ├── config.py            # config.yaml + .env → typed constants
│   ├── persistence.py       # BaseConfig: atomic JSON load/save; GuildConfig subclass
│   ├── guild_config.py      # Per-guild settings + validated setters
│   ├── dice.py              # Dice grammar and scoring — no strings for humans
│   ├── format.py            # Renders a RollResult as text (Discord markdown)
│   └── message.py           # MessageWriter: every embed the bot sends
│
├── data/
│   ├── guild_config.json    # Per-guild settings (gitignored)
│   └── logs/                # Rotating log files (gitignored, .gitkeep only)
│
└── tests/
    ├── conftest.py          # Fixtures: mock_bot, ctx, seeded_rng + sent_embed() helper
    ├── test_config.py
    ├── test_persistence.py  # Including the atomic-write guarantees
    ├── test_dice.py         # Grammar, limits, keep modes
    ├── test_successes.py    # Hit counting, the botch rule, outcomes
    ├── test_format.py       # Breakdowns, notation, the code-span rule
    ├── test_guild_config.py
    ├── test_message.py
    ├── test_roll_cog.py
    ├── test_settings_cog.py
    ├── test_invite_cog.py
    └── test_help_cog.py     # Help cog + the documentation drift guards
```

---

## Configuration

### config.yaml — locality file

Everything that makes this bot *this* bot. Two sections: `bot:` (name, prefix,
version base, embed colour, invite URL, emojis) and `dice:` (defaults and
limits). Keys named `default_*` are per-guild overridable; `max_*` are abuse
guards, not allow-lists.

`invite_url` is **empty** until the Discord application exists. The invite
reply says so rather than sending a blank link.

### .env — secrets only

`DISCORD_TOKEN`, `OWNER_ID`, `DEV_GUILD_ID`. Never committed; `.env.example`
is the template. Read once via `load_dotenv` in `utils/config.py`, then with
`os.getenv` at the point of use.

### utils/config.py

Loads both files at import time and exports typed `SCREAMING_SNAKE` constants.

`VERSION` is built from git at import: `{base}.{commit count} ({short hash})`,
e.g. `1.0.42 (a1b2c3d)`. That makes `!version` a deploy check — if the hash is
not what was pushed, the restart did not take.

**Every runtime path hangs off `BASE_DIR`.** `DATA_DIR`, `LOGS_DIR`,
`GUILD_CONFIG_FILE`. Directories are created on import; JSON files are created
lazily on first save, so a fresh install starts with none of them. Nothing in
`cogs/` may construct a `data/` path — add a constant here instead.

---

## Core Utils

### utils/dice.py — the engine

Data and scoring only. No Discord types **and no rendering** — turning a
result into text lives in `utils/format.py`, so the engine reads and tests
without presentation in the way. (This is the one place Chronicler diverges
from the Night Roller port, where `breakdown()` and friends sat on the result
object and emitted Discord markdown from the "pure" module.)

```python
class DiceError(ValueError)                 # anything the user can fix by retyping

@dataclass
class DiceGroup:                            # one NdM term and the faces it rolled
    count, sides, rolls, dropped, negative
    notation -> str                         # "2d6"
    subtotal -> int                         # sum, negated if negative

@dataclass
class RollResult:
    expression, groups, modifier, total, keep, target, subtract_ones
    counts_successes, faces, hits, ones, net_hits, outcome
    is_single_d20, natural

def parse(expression) -> tuple[list[DiceGroup], int]    # validates, does not roll
def roll(expression, *, keep, target, subtract_ones, rng) -> RollResult
```

**Grammar:** `expression := term (('+'|'-') term)*`, `term := [count]'d'sides |
constant`. Whitespace and case insensitive. Strict: every term after the first
needs a sign, and the whole string must be consumed, which is what rejects
`1d6d4`. Die sizes are open-ended by design.

**Success counting** is switched on purely by passing `target`. `hits` counts
faces at or above it, `ones` counts 1s when the botch rule is on, `net_hits`
is the difference.

**The outcome rule:** `net_hits > 0` is a success; otherwise any 1 on the
table makes it a **botch** — including successes cancelled exactly to zero —
and no 1s makes it a plain failure. With `subtract_ones=False`, `ones` is
always 0, so a botch is impossible by construction.

**Advantage** is `keep='high'|'low'`, which keeps the single best or worst die
of the *first group only* and moves the rest to `dropped`. Dropped dice are
excluded from `faces`, so they cannot score.

**Determinism:** pass `rng=random.Random(seed)`, or an RNG whose `randint`
deals a fixed sequence of faces — that is how the success tests work.

### utils/format.py — rendering a roll

Between the engine and the embeds. Emits Discord-flavoured markdown but
imports no Discord types, so it is as testable as the engine.

`breakdown(result)` lists every face (`[4, 6] + 3`), bolding hits,
underlining cancelling 1s and striking dropped dice.
`compact_breakdown(result)` substitutes per-group subtotals (`2d6(10) + 3`)
for rolls too large to print.
`notation(result)` is the signed dice notation (`2d6 - 1d4`).
`wrap(detail)` adds a code span **only** when the text carries no markup —
Discord renders nothing inside a code span, so a bolded breakdown has to go
out bare or readers see literal `**`.

### utils/persistence.py + utils/guild_config.py

`BaseConfig` is a JSON-dict wrapper with no caching: every call re-reads the
file. Subclasses set `path`, importing the constant *late* so the path is read
at construction time — which is also what lets tests redirect the store by
patching `utils.config.GUILD_CONFIG_FILE`.

**Writes are atomic**: data goes to a `.tmp` beside the target, is flushed and
fsynced, then moved into place with `os.replace`. A crash mid-write leaves the
previous version intact, and no temp file is left behind on failure. This is a
deliberate departure from the other two bots, which truncate and rewrite —
fine for an occasional `!config` edit, wrong for a reminder loop writing on a
timer beside players editing their own records.

Each concern gets its own file and subclass, so a problem in one store cannot
take the others down.

`guild_config.py` is a module of functions over a `GuildConfig()` instance,
in four tiers: generic `get_setting`/`set_setting`/`reset_guild`/
`get_all_settings` keyed by `str(guild_id)` over a `_DEFAULTS` dict built from
config constants; typed accessors (`get_die`, `is_wod`, …); **validated
setters** that raise `SettingError` whose message is shown to the user
verbatim; and config re-exports so cogs need not import `utils.config`.

Validation belongs here, not in the cog, because it can cross-check settings —
`set_difficulty` refuses a target above the current die and names the command
that would fix it.

### utils/message.py — MessageWriter

Every embed the bot sends. Each method is a `@staticmethod` that **returns**
an embed; cogs do the sending. Colour and emojis come from `config.yaml`; the
green/red accents are module-local.

`success` / `error` / `info` are the generic three. `config_card` renders the
settings card. `invite` handles the unset-URL case. `help_page` carries a page
counter instead of the bot-name footer — which is why the help cog cannot just
use `info()`, and why it does not build embeds inline the way echo-bot's does.

`roll_card` is the domain embed: it picks emoji, colour and flavour (natural
20/1, or success/failure/botch), prints the headline with `#` markdown, and
degrades output in two stages — full breakdown, then per-group subtotals, then
nothing — against `_MAX_TITLE_NOTATION` and `_MAX_BREAKDOWN`.

---

## Cogs

Each is `class XCog(commands.Cog, name='X')` with an `async def setup(bot)`
footer. User-facing commands are `@commands.hybrid_command` /
`hybrid_group`, so one definition serves `!cmd` and `/cmd`; the docstring
becomes the slash description. Owner plumbing uses plain `@commands.command`
with `hidden=True` so it stays out of help and out of the coverage test.

### cogs/roll.py

All parsing is in module-level pure functions *above* the class, so tests
reach them without a cog: `split_input` (keep mode, expression, target,
reason), `advantage_expression` (doubles the first group so there are two dice
to choose from), `is_bare_pool`, `resolve_expression`. The method is pure
orchestration — parse, validate, resolve, roll, log, one `ctx.send`.

In a WoD server a bare pool is auto-scored against the server difficulty;
explicit notation like `2d6+3d8` is left summing unless `(n)` is given.

### cogs/settings.py

`cog_check` raises `NoPrivateMessage` outside a guild; `manage_guild` is
required on **every** subcommand (the group decorator does not cover
children). Every mutation ends by re-rendering the settings card through a
private `_show`, so the user always sees resulting state rather than a bare
confirmation.

### cogs/help.py

Paginated. `_PAGES` maps a page key to title and body templates; `_render`
fills them in from the guild's settings, so the rolling page shows the
server's die and the matching system note. `_HelpView` is a
`discord.ui.View` with prev/next buttons that disable at the ends, 120 s
timeout. `!help <section>` jumps straight to a page; an unknown name falls
back to the overview.

Bodies must name every visible command with its prefix, and must not name
anything that is not a command — both directions are tested.

### cogs/invite.py

No command, just an `on_message` listener guarded to DMs, with the matching in
a testable module function `is_invite_request`.

### cogs/dev.py

`!version`, `!ping`, and owner-only hidden `!restart` (close and `sys.exit(0)`
so systemd restarts) and `!sync` (push slash commands to a guild or globally).

---

## Entry Point (bot.py)

Order matters. The **SSL patch is first, before any other import** — it
rewrites `ssl.create_default_context` to use `certifi`, which the Pi needs.

Then logging: one timestamped `RotatingFileHandler` per process start
(`chronicler_<stamp>.log`, 2 MB, 3 backups) plus a console handler at INFO,
configured at module level. `discord` and `discord.http` are pinned to
WARNING.

Then the bot: `Intents.default()` with `message_content`, `help_command=None`
so the help cog owns `!help`, and an explicit ordered `_COGS` list — no
dynamic discovery.

`setup_hook` is not used. Slash syncing happens in `on_ready`, and **only to
`DEV_GUILD_ID`** — global commands propagate on Discord's own schedule, and
`!sync` is the manual lever.

`on_command_error` swallows `CommandNotFound`, names a missing argument,
answers permission failures with plain text, and logs everything else with
`exc_info`. These are the only sanctioned non-embed sends.

---

## Deployment

systemd on the Pi (`chronicler.service`), updated by a path-filtered GitHub
Actions workflow (`.github/workflows/deploy-chronicler.yml`) on the repo-wide
self-hosted runner — no new runner needed for a third bot. `auto_update.sh` is
the cron fallback. No `pm2.config.js`: it is dead weight in echo-bot and
night-roller already omits it.

**Every deploy restarts the process.** Anything time-sensitive must survive a
restart on disk.

See `LINUX_SETUP.md`.

---

## Testing

`pytest.ini` sets `asyncio_mode = auto`, so test coroutines need no marker.
Run from the `chronicler/` folder with `python -m pytest` — the documentation
guards open `help.md` and `FEATURES.md` by relative path.

### Fixtures (tests/conftest.py)

`isolated_guild_config` is **autouse**: it points `GUILD_CONFIG_FILE` at
`tmp_path`, so no test ever writes to the real `data/`. `mock_bot` and `ctx`
are plain mocks with only the attributes cogs touch. `wod_guild` configures
the test guild for World of Darkness by calling the real setter.
`seeded_rng` gives reproducible dice. `sent_embed(ctx)` is a module-level
function, imported as `from conftest import sent_embed`.

### How cogs are tested

No `Bot`, no extension loading. Instantiate the cog with `mock_bot` and invoke
`.callback(cog, ctx, ...)` to bypass the decorator machinery, then assert on
the embed — substring checks, never exact strings. Settings tests assert
through the real accessors afterwards, which also proves persistence.

### The documentation guards

`tests/test_help_cog.py` discovers the real command set by importing each
`cogs/*.py`, finding the `Cog` subclasses defined there, instantiating them
with a mock bot and walking `get_commands()` recursively. Cog classes are
inspected directly rather than loaded into a `Bot`, because loading extensions
mutates shared command state and leaks between test modules.

It then asserts, in both directions:

- every non-hidden command and subcommand is named in the rendered help pages,
  in `help.md`, **and in `FEATURES.md`**;
- nothing named with a prefix in any of the three still fails to exist.

Subcommands must be named in full (`!config die`), under the group's own name
or any alias. `hidden=True` is the opt-out. That is what makes the feature
list self-enforcing rather than a promise.

---

## Build Phases

1. **Skeleton + dice** — done. Spine, config, persistence, embeds, dice
   ported, settings/help/dev/invite, full test suite, docs, CI workflow.
2. **Discord application and deployment** — create the app, set permissions
   and the invite URL, deploy to the Pi, document moving it to another server.
3. **Chronicle of Darkness dice** — a third roll system: 10-again (and
   9-/8-again), rote rerolls, chance die, exceptional success at 5+.
4. **Announcements and reminders** — the only greenfield architecture here.
   Needs persisted due times reconciled on `on_ready`, a decided answer for
   reminders missed while the bot was down, per-guild channel targeting, and a
   timezone. `echo-bot/utils/devlog.py` has the task-lifecycle idiom and
   `echo-bot/utils/intro_config.py` the `MON-FRI`/`WEEKEND` day vocabulary.
5. **Character builder** — CofD sheets per user per server.
6. **Session notes** — timestamped entries per server.

Phases 5 and 6 introduce user-authored free text retained indefinitely, which
is a new data category for this repo. Retention and deletion must be decided
with the storage, and the root `PRIVACY_POLICY.md` and `TERMS_OF_SERVICE.md`
updated when they land.

---

## Rules for Working on chronicler

- Read this file first.
- All runtime paths come from `utils/config.py` constants — never hardcode
  `data/` in a cog.
- All embeds come from `MessageWriter` — never build `discord.Embed` in a cog.
- Dice logic stays in `utils/dice.py`, free of Discord types *and* of
  rendering; rendering goes in `utils/format.py`.
- Character, note and reminder logic will follow the same rule: pure modules
  in `utils/`, cogs only parse and present.
- Every change ships with tests. Run `python -m pytest` from `chronicler/`
  before committing.
- Adding, removing or renaming a command means updating `help.md` **and**
  `FEATURES.md`. The suite will fail if you forget.
