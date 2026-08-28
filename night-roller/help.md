# Night Roller — Command Reference

A dice bot for D&D. All commands work with the `!` prefix and as `/` slash commands.

---

## Rolling

| Command | Aliases | Description |
|---|---|---|
| `!roll` | `!r` | Roll one of this server's default die |
| `!roll <n>` | `!r` | Roll a pool of `n` default dice — e.g. `!roll 5` |
| `!roll <expression>` | `!r` | Roll a dice expression |
| `!roll <dice> (<n>)` | `!r` | Count how many dice land on `n` or higher |
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

## Counting successes (dice pools)

Put a target number in parentheses and the roll is scored as **hits** instead of a sum: every die at or above the target counts as one success.

| Command | Meaning |
|---|---|
| `!roll 5 (6)` | roll 5 default dice, count those showing 6+ |
| `!roll 6d10 (7)` | roll 6d10, count those showing 7+ |
| `!roll 5 (5) intimidate` | same, with a label |

Hits are shown in **bold** in the breakdown.

### World of Darkness servers

Run `!config system wod` and the server switches to WoD scoring:

- the default die becomes **d10**
- a plain `!roll 5` is scored against the server difficulty (default **6**) with no need to type `(6)`
- **each `1` cancels a success** — underlined in the breakdown
- **Botch** — any 1 came up and no success survived it, including successes cancelled exactly down to zero
- **Failure** — nothing hit the target and no 1s were rolled
- **Success** — at least one success survives after the 1s cancel

```
!roll 5          ->  5d10 · difficulty 6   3 successes   [8, 3, 9, 10, 2]
!roll 5 (5)      ->  5d10 · difficulty 5   Botch         [1, 7, 2, 6, 1]  (2 hits - 2 ones)
!roll 2d6+3d8    ->  still a plain sum — explicit dice notation is never rescored
```

---

## Server settings

Requires the **Manage Server** permission. Settings are per server and persist across restarts.

| Command | Description |
|---|---|
| `!config` | Show this server's roll settings |
| `!config system <standard\|wod>` | Switch scoring system (`wod` also sets the die to d10) |
| `!config die <sides>` | Default die for pool rolls — `!roll 5` becomes `5d<sides>` |
| `!config difficulty <n>` | Default success target for WoD rolls |
| `!config ones <on\|off>` | Whether each `1` cancels a success |
| `!config reset` | Drop all overrides, back to global defaults |

Alias: `!settings`.

---

## Direct messages

DM the bot **`join`** (or `invite` / `add`) and it replies with the URL for adding it to a server. Case doesn't matter, and a leading `!` is fine.

Commands work in DMs too — `!roll 2d6+3` in a DM rolls normally.

---

## Other

| Command | Description |
|---|---|
| `!help` | Show the command list |
| `!version` | Show the running version (base version + commit count + hash) |
| `!ping` | Gateway latency |
| `!restart` | **Owner only** — exit so systemd restarts the bot |
