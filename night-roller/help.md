# Night Roller — Command Reference

A dice bot for D&D. All commands work with the `!` prefix and as `/` slash commands.

---

## Rolling

| Command | Aliases | Description |
|---|---|---|
| `!roll` | `!r` | Roll the default die (`d20`) |
| `!roll <expression>` | `!r` | Roll a dice expression |
| `!roll adv [modifier]` | — | Advantage — rolls two d20 and keeps the highest |
| `!roll dis [modifier]` | — | Disadvantage — rolls two d20 and keeps the lowest |
| `!roll <expression> <label>` | — | Anything after the dice is shown as a label on the result |

### Expression syntax

`[count]d<sides>` terms joined by `+` or `-`, plus optional flat modifiers.

**Any die size works.** `d<sides>` is not limited to the standard set — `d3`, `d7`, `d37`, `d144` are all valid, alongside the usual d4/d6/d8/d10/d12/d20/d100.

**Any number of dice groups.** Chain as many `xdy` terms as you like with `+` or `-`.

| Example | Meaning |
|---|---|
| `!roll` | one d20 |
| `!roll d100` | one d100 |
| `!roll d7` | one d7 — non-standard sizes are fine |
| `!roll 2d6+3` | two d6, plus 3 |
| `!roll 4d6-1` | four d6, minus 1 |
| `!roll 2d6+3d8` | two d6 and three d8 |
| `!roll 4d6+2d10+1d4+3d12+2d20` | as many groups as you need |
| `!roll d20+2d4+1` | a d20, two d4 and a flat +1 |
| `!roll 2d6-1d4` | two d6 minus one d4 |
| `!roll 2d6 + 3d8` | spaces around the operators are fine |
| `!roll adv +5` | two d20 keep highest, plus 5 |
| `!roll dis` | two d20 keep the lowest |
| `!roll 2d6+3 sneak attack` | rolls `2d6+3`, labelled "sneak attack" |

Advantage words: `adv`, `advantage`, `a` · Disadvantage words: `dis`, `disadv`, `disadvantage`

A lone d20 that comes up **20** or **1** is called out as a natural 20 / natural 1.

### Limits

These are abuse guards, not a list of allowed dice — raise them in `config.yaml` any time.

| Limit | Default |
|---|---|
| Dice per group | 500 |
| Die size | d10000 |
| Groups per expression | 25 |

Rolls too large to print die by die collapse to per-group subtotals — `300d20(3193)` — so the result always fits in one message.

---

## Other

| Command | Description |
|---|---|
| `!help` | Show the command list |
| `!version` | Show the running version (base version + commit count + hash) |
| `!ping` | Gateway latency |
| `!restart` | **Owner only** — exit so systemd restarts the bot |
