# AGENTS.md — Project Rules

## Commit rules
- **Never** add `Co-Authored-By` lines to commit messages.
- **Never** mention AI, agents, or any assistant in commit messages, pull request
  descriptions, or code comments. Commits read as the author's own work.
- **Always** commit and push after every change. Do not leave work uncommitted.
- Before staging new work, run `git status`. If there are unstaged changes, **ask the user** what to do with them before proceeding.

## Session start
- At the start of every session involving `echo-bot/`, read `echo-bot/ARCHITECTURE.md` before touching any code.
- At the start of every session involving `night-roller/`, read `night-roller/ARCHITECTURE.md` before touching any code.
- At the start of every session involving `chronicler/`, read `chronicler/ARCHITECTURE.md` before touching any code.

## Help files

### echo-bot
- Whenever a command is added, removed, or renamed: update `echo-bot/help.md`.
- Help updates are mandatory, not optional.
- Enforced: `echo-bot/tests/test_help_cog.py` fails if a command is missing from
  the `!help` pages or `help.md`, or if either names a command that no longer
  exists. Doc examples that merely look like commands go in its
  `_TRIGGER_EXAMPLES` allowlist.

### night-roller
- Whenever a command is added, removed, or renamed: update `night-roller/help.md`.
- Help updates are mandatory, not optional.

### chronicler
- Whenever a command is added, removed, or renamed: update `chronicler/help.md`.
- Help updates are mandatory, not optional.
- Enforced: `chronicler/tests/test_help_cog.py` fails if a command is missing from
  the help pages or `help.md`, or if either names a command that no longer exists.

## Feature lists
Each bot keeps a `FEATURES.md` in its folder — the always-current list of what the
bot does. Whenever a command is added, removed, or renamed, update it in the same
change. This is mandatory, not optional.

### chronicler / echo-bot
- `chronicler/FEATURES.md` and `echo-bot/FEATURES.md` both exist and are
  **test-enforced** by each bot's `tests/test_help_cog.py`, in both directions:
  no undocumented command, no documented command that no longer exists.
- The stale-command check scans the **whole file**, including `## Planned` and
  `## Withdrawn`. So a planned feature may be described in prose but must not be
  written as a `!command` until that command exists.

### night-roller
- Has no `FEATURES.md`, and its `help.md` is unguarded — nothing tests that it
  matches the real command set, so it may already have drifted. It is being
  retired, so this is left as is; write one only if that changes.
- Until then, keep its `### Features` list in the root `README.md` current.

## Tests

### echo-bot
- Every code change must include corresponding tests in `echo-bot/tests/`.
- Run the test suite (`pytest` from `echo-bot/`) before committing.
- New commands → new test cases in the relevant cog test file.
- New utility functions → new test cases in the relevant util test file.

### night-roller
- Every code change must include corresponding tests in `night-roller/tests/`.
- Run the test suite (`pytest` from `night-roller/`) before committing.
- New commands → new test cases in the relevant cog test file.
- New utility functions → new test cases in the relevant util test file.

### chronicler
- Every code change must include corresponding tests in `chronicler/tests/`.
- Run the test suite (`python -m pytest` from `chronicler/`) before committing. It
  must be run from that folder — the documentation guards open `help.md` and
  `FEATURES.md` by relative path.
- New commands → new test cases in the relevant cog test file.
- New utility functions → new test cases in the relevant util test file.

## Architecture
- `echo-bot/ARCHITECTURE.md` — architecture reference for Echo. Update it when structure changes.
- `night-roller/ARCHITECTURE.md` — architecture reference for Night Roller. Update it when structure changes.
- `chronicler/ARCHITECTURE.md` — architecture reference for Chronicler. Update it when structure changes.

## Code rules (echo-bot)
- All runtime paths must be derived from `utils/config.py` constants — never hardcode `data/` paths in cogs.
- All Discord embeds must use `MessageWriter` — never build `discord.Embed` inline in cogs.
- All voice interactions must go through `VoiceStreamer` — never call `VoiceClient` methods directly in cogs.

## Code rules (night-roller)
- All runtime paths must be derived from `utils/config.py` constants — never hardcode `data/` paths in cogs.
- All Discord embeds must use `MessageWriter` — never build `discord.Embed` inline in cogs.
- All dice logic lives in `utils/dice.py` and stays free of Discord types — cogs only parse input and present results.

## Code rules (chronicler)
- All runtime paths must be derived from `utils/config.py` constants — never hardcode `data/` paths in cogs.
- All Discord embeds must use `MessageWriter` — never build `discord.Embed` inline in cogs.
- All dice logic lives in `utils/dice.py` and stays free of Discord types **and of
  rendering** — turning a result into text belongs in `utils/format.py`.
- Archive logic lives in `utils/archive.py` and `utils/transcript.py`, free of Discord
  types. The cog fetches history, downloads attachments, zips and sends.
- Character, note and reminder logic follows the same split: pure modules in `utils/`,
  with cogs only parsing input and presenting results.
- Persisted data goes through `utils/persistence.py`, which writes atomically. Do not
  write JSON directly from a cog.
- **Never delete a Discord message except against a manifest read out of an export
  bundle that exists on disk.** The audit trail in `data/archive_config.json` is not
  sufficient authority — if the backup is gone, refuse.
- Document rendering must stay pure-Python (`fpdf2`, `python-docx`, `Pillow`). Do not
  introduce a dependency needing system libraries: the Pi deploy only runs
  `pip install -r requirements.txt` and cannot `apt install` anything.
- Chronicler needs **Python 3.11+** because of those two libraries, where echo-bot and
  night-roller run on 3.8. Pin minimum versions in `requirements.txt` for anything with
  a Python floor, so an old interpreter fails at install rather than silently resolving
  to a release missing the APIs in use.

## Bots in this repo
| Folder | Description | Status |
|---|---|---|
| `echo-bot/` | Echo — audio, soundboard, intros, TTS, future voice listen | **Active** |
| `night-roller/` | Night Roller — D&D dice roller (`!roll`) | **Superseded** by Chronicler; stays until Chronicler ships, then retired |
| `chronicler/` | Chronicler — tabletop chronicle keeper: dice and channel archiving, plus planned announcements, character builder and session notes | **Active** — dice and archive export built, not yet deployed |
