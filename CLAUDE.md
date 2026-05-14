# CLAUDE.md — Project Rules

## Commit rules
- **Never** add `Co-Authored-By` lines to commit messages.
- **Always** commit and push after every change. Do not leave work uncommitted.
- Before staging new work, run `git status`. If there are unstaged changes, **ask the user** what to do with them before proceeding.

## Session start
- At the start of every session involving `echo-bot/`, read `echo-bot/ARCHITECTURE.md` before touching any code.
- `music-bot/` is **frozen** — do not modify it under any circumstances.

## Help files

### echo-bot
- Whenever a command is added, removed, or renamed: update `echo-bot/help.md`.
- Help updates are mandatory, not optional.

### music-bot (frozen — for reference only)
- `music-bot/help.md` and `_HELP_TEXT` in `music-bot/cogs/music.py` are not to be modified.

## Tests

### echo-bot
- Every code change must include corresponding tests in `echo-bot/tests/`.
- Run the test suite (`pytest` from `echo-bot/`) before committing.
- New commands → new test cases in the relevant cog test file.
- New utility functions → new test cases in the relevant util test file.

### music-bot (frozen)
- Do not run or modify music-bot tests.

## Architecture
- `echo-bot/ARCHITECTURE.md` — primary architecture reference for the active bot. Update it when structure changes.
- `music-bot/ARCHITECTURE.md` — frozen, do not modify.

## Code rules (echo-bot)
- All runtime paths must be derived from `utils/config.py` constants — never hardcode `data/` paths in cogs.
- All Discord embeds must use `MessageWriter` — never build `discord.Embed` inline in cogs.
- All voice interactions must go through `VoiceStreamer` — never call `VoiceClient` methods directly in cogs.

## Bots in this repo
| Folder | Description | Status |
|---|---|---|
| `echo-bot/` | Echo — audio, soundboard, intros, TTS, future voice listen | **Active** |
| `music-bot/` | Legacy music bot — YouTube, Suno, playlists, intro sounds | **Frozen** |
