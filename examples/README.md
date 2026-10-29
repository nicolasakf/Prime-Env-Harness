# Examples

Three complete environments, each with behavioral checks and a suggested execution
policy. The first two also ship a notebook report template and an optional replay
viewer.

| Directory | Seats | What it is |
| --- | --- | --- |
| [`texas-holdem`](texas-holdem) | 2 to 9, human or agent | Fixed-hand no-limit Texas Hold'em with play chips, private cards, side pots, and no table talk. Setup: hands, starting chips, blinds. |
| [`market-making-card-game`](market-making-card-game) | 2, human or agent | Two players trade a contract that settles to the sum of all card ranks, with private hole cards, public community cards, and cumulative P&L. Each agent request carries its full current state instead of the transcript. |
| [`function-discovery`](function-discovery) | 1, human or agent | One solver probes hidden functions with batched queries under a per-function budget, keeps a scratchpad, then submits a sandboxed Python `f` per function. The score is the share of hidden test cases passed. Ships 25 functions in five tiers (starter, easy, medium, hard, extreme), from arithmetic to string rules, parsers, and a hidden state machine; edit `functions.py` to change the game. Setup: queries per function, function ids, tiers. Participant Python is requested; Docker is recommended. |

## Install

From the repository root:

```bash
python3 scripts/install_examples.py            # every example
python3 scripts/install_examples.py texas-holdem
```

Add `--data-dir <directory>` if you launch Prime Env with a custom data
directory. The script copies each example into a fresh builder draft, installs its
report template and any viewer, and prints the commands to finish. It does not run or save
anything. Then, in Prime Env:

```text
/env policy <draft-path> {"backend":"local"}
/env validate <draft-path>
/env save <draft-path> <id>
/env enter <id>
```

Or tell the agent: "validate and save the new drafts, then let me play
texas-holdem against an agent". Every example uses pure-Python rules with no
dependencies, so `local` execution is enough and Docker is not required.
`function-discovery` also runs model-written code and lets the agent use participant
Python, so its suggested policy uses Docker; `local` works but gives that code
host-user permissions.

## Reports

After a run finishes, ask for a report ("make a report for that run"). The
`game-report` template under each example turns the run's recorded actions into
charts and tables. The Hold'em template was verified on the version shipped here.
The market template was verified on an earlier version that differs only in the
acknowledgment returned by `say` and the added `frame` method for live viewing, and
is marked compatible with the shipped version without a separate run.

## Viewer

Each example's `viewer/` folder draws its game, with hand-by-hand chapter marks.
`texas-holdem/viewer/` shows seats, cards, bets, the board, each hand's showdown,
a hand log, and stacks by hand. `market-making-card-game/viewer/` shows both
players' cards, positions, and cash, the community cards as they are revealed, the
current bid and ask with who owns each side, a hand log, how each hand settled, and
cumulative P&L by hand. Either one replays an ended run with every card face up
("show me a replay of that run"), and follows a running one live with `/env view`:
at the table you see your own cards and everyone else's face down, and
`/env view public` hides them all. Only runs recorded with snapshot history can be
replayed.
Viewers are optional; other environments have none unless you ask the builder
for one.

## Design notes

[`design-notes/`](design-notes) holds the reasoning behind changes to an example.
