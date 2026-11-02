# Changelog

All notable changes to Prime Env Harness are listed here. The release workflow
publishes the section matching a tag as that release's notes, so every tagged
version needs a `## <version> - <date>` heading.

## 0.1.1 - 2026-11-02

The first public release. Prime Env Harness started from
[Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent) by Prime Intellect
and is now an independent project.

### What you can do

- **Build an environment by conversation.** Describe a card game, negotiation,
  document workflow, or simulation; the builder agent asks about rules, seats,
  turn flow, privacy, deadlines, and failure handling before it writes the
  environment in Python or TypeScript.
- **Test before anyone plays.** Environments ship behavioral checks that must pass,
  and saved definitions are immutable, content-addressed versions, so a result
  always names the exact rules that produced it.
- **Run humans and models at the same table.** One human and one agent, several
  agent seats, or agents only. Each agent's reasoning stays in a private seat
  session and never reaches other participants.
- **Control execution.** Choose local or Docker per run, and grant networking,
  mounts, secrets, and integrations explicitly.
- **Evaluate and review.** Runs persist every action and receipt, survive crashes,
  can be paused and resumed, and can be turned into notebook reports. Environments
  can register replay and live viewers.
- **Everything is available from `/env`** (create, policy, validate, save, enter,
  act, leave, resume) or by talking to the agent.

### Included examples

- `texas-holdem`: no-limit Texas Hold'em for 2 to 9 seats with private cards, a game
  report, and a viewer.
- `market-making-card-game`: a two-player market-making game with cumulative P&L,
  stateless agents, a game report, and a viewer.

### Distribution

- Prebuilt tarballs for Linux (x64, arm64; glibc 2.35 or newer) and macOS (x64,
  arm64), each with a published SHA-256, plus `install.sh`.
- Prime Env Harness keeps its settings, credentials, sessions, and environments in
  `~/.prime-env-harness`, separate from any Prime Agent installation.

### Known limitations

- Local execution is not a sandbox; use Docker for anything you do not trust.
- There is no prebuilt Windows binary yet.
- The in-app updater is disabled. Update by running the installer again.
- Prime Env Harness does not train or fine-tune models.
