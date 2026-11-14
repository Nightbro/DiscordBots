# CLAUDE.md — Project Rules

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

### chronicler
- `chronicler/FEATURES.md` exists and is **test-enforced** by
  `chronicler/tests/test_help_cog.py`, in both directions: no undocumented command,
  no documented command that no longer exists.

### echo-bot / night-roller
- Neither has a `FEATURES.md` yet; their feature lists currently live in the root
  `README.md`. Write one when next working in either folder, following
  `chronicler/FEATURES.md` as the pattern.
- Until then, keep the `### Features` list in the root `README.md` current for those
  two bots.

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
- Character, note and reminder logic follows the same split: pure modules in `utils/`,
  with cogs only parsing input and presenting results.
- Persisted data goes through `utils/persistence.py`, which writes atomically. Do not
  write JSON directly from a cog.

## Bots in this repo
| Folder | Description | Status |
|---|---|---|
| `echo-bot/` | Echo — audio, soundboard, intros, TTS, future voice listen | **Active** |
| `night-roller/` | Night Roller — D&D dice roller (`!roll`) | **Superseded** by Chronicler; stays until Chronicler ships, then retired |
| `chronicler/` | Chronicler — tabletop chronicle keeper: dice, plus planned announcements, character builder and session notes | **Active** — dice built, not yet deployed |
