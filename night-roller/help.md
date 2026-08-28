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

| Example | Meaning |
|---|---|
| `!roll` | one d20 |
| `!roll d100` | one d100 |
| `!roll 2d6+3` | two d6, plus 3 |
| `!roll 4d6-1` | four d6, minus 1 |
| `!roll d20+2d4+1` | a d20, two d4 and a flat +1 |
| `!roll 2d6-1d4` | two d6 minus one d4 |
| `!roll adv +5` | two d20 keep highest, plus 5 |
| `!roll dis` | two d20 keep the lowest |
| `!roll 2d6+3 sneak attack` | rolls `2d6+3`, labelled "sneak attack" |

Advantage words: `adv`, `advantage`, `a` · Disadvantage words: `dis`, `disadv`, `disadvantage`

A lone d20 that comes up **20** or **1** is called out as a natural 20 / natural 1.

### Limits

Set in `config.yaml` — up to 100 dice per group, d1000 maximum, 10 groups per expression.

---

## Other

| Command | Description |
|---|---|
| `!help` | Show the command list |
| `!version` | Show the running version (base version + commit count + hash) |
| `!ping` | Gateway latency |
| `!restart` | **Owner only** — exit so systemd restarts the bot |
