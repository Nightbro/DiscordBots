# CLAUDE.md — Project Rules

## Commit rules
- **Never** add `Co-Authored-By` lines to commit messages.
- **Always** commit and push after every change. Do not leave work uncommitted.
- Before staging new work, run `git status`. If there are unstaged changes, **ask the user** what to do with them before proceeding.

## Session start
- At the start of every session involving `echo-bot/`, read `echo-bot/ARCHITECTURE.md` before touching any code.
- At the start of every session involving `night-roller/`, read `night-roller/ARCHITECTURE.md` before touching any code.

## Help files

### echo-bot
- Whenever a command is added, removed, or renamed: update `echo-bot/help.md`.
- Help updates are mandatory, not optional.

### night-roller
- Whenever a command is added, removed, or renamed: update `night-roller/help.md`.
- Help updates are mandatory, not optional.

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

## Architecture
- `echo-bot/ARCHITECTURE.md` — architecture reference for Echo. Update it when structure changes.
- `night-roller/ARCHITECTURE.md` — architecture reference for Night Roller. Update it when structure changes.

## Code rules (echo-bot)
- All runtime paths must be derived from `utils/config.py` constants — never hardcode `data/` paths in cogs.
- All Discord embeds must use `MessageWriter` — never build `discord.Embed` inline in cogs.
- All voice interactions must go through `VoiceStreamer` — never call `VoiceClient` methods directly in cogs.

## Code rules (night-roller)
- All runtime paths must be derived from `utils/config.py` constants — never hardcode `data/` paths in cogs.
- All Discord embeds must use `MessageWriter` — never build `discord.Embed` inline in cogs.
- All dice logic lives in `utils/dice.py` and stays free of Discord types — cogs only parse input and present results.

## Bots in this repo
| Folder | Description | Status |
|---|---|---|
| `echo-bot/` | Echo — audio, soundboard, intros, TTS, future voice listen | **Active** |
| `night-roller/` | Night Roller — D&D dice roller (`!roll`) | **Active** |
