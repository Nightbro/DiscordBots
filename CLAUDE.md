# CLAUDE.md — Project Rules

## Commit rules
- **Never** add `Co-Authored-By` lines to commit messages.
- **Always** commit and push after every change. Do not leave work uncommitted.
- Before staging new work, run `git status`. If there are unstaged changes, **ask the user** what to do with them before proceeding.

## Help files
- Whenever a command is added, removed, or renamed: update **both**:
  - `music-bot/help.md` — the markdown reference file
  - `_HELP_TEXT` constant in `music-bot/cogs/music.py` — what `!help` shows in Discord
- Help updates are mandatory, not optional.

## Tests
- Every code change must include corresponding tests in `music-bot/tests/`.
- Run the test suite (`pytest` from `music-bot/`) before committing to verify nothing broke.
- New commands → new test cases in the relevant cog test file.
- New utility functions → new test cases in the relevant utils test file.

## Architecture
See `music-bot/ARCHITECTURE.md` for the full architecture description. Update it when the structure changes.

## Bots in this repo
| Folder | Description |
|---|---|
| `music-bot/` | Discord music bot — YouTube, Suno, playlists, intro sounds |
