# AGENTS.md

Development rules for Prime Env Harness (Rust) on nicolasakf/prime-env-harness, branch `main`.
Prime Env Harness started from Prime Agent (PrimeIntellect-ai/prime-agent) and is now an independent project; see "Relationship to Prime Agent" below.
Every contributor (human or agent) must read this before working on this repo.

## Environment vs harness (read before planning any change)

This project has two layers, and every change belongs to exactly one of them. Before you
edit anything, decide which layer the change is for and say so in your plan.

- **Environment**: one specific environment's content: its definition, rules, actions,
  views, prompts, policy, seat/role behavior, data, and its tests. It lives only in that
  environment's own files: the definition under `~/.prime-env-harness/environments/`
  (user data, never in this repo), and in-repo only its fixture directory
  `crates/pa-environments/fixtures/<env>/`, its shipped example under `examples/<env>/`,
  plus its dedicated test file in
  `crates/pa-environments/tests/` (for example `fixtures/card_market/` and
  `tests/card_market.rs`).
- **Harness**: everything that works for any environment: the `pa-environments` runtime,
  broker, runner, SDKs, and Docker images; the `pa-core`, `pa-daemon`, `pa-tui`, and
  `pa-cli` code; the `environments_v1` extension and `/env` UI; the prompt layers; the
  `skills/` and `docs/` that describe them.

Rules:

- **Never change the harness to fix, tune, or special-case one environment.** If a
  problem shows up in one environment, fix it in that environment's files first. Touch the
  harness only when the defect or missing capability is genuinely environment-independent
  and you can state it without naming the environment.
- No environment names, ids, rules, or vocabulary (card, market, bid, relay, and the like)
  in harness code, prompt layers, skills, docs, or harness tests. No `if env == ...`
  branches, no per-environment constants, no behavior keyed on a definition id.
  Harness tests and docs use generic examples or a neutral fixture.
- If a fix needs both, split it: the harness change is generic, lands as its own logical
  change, and is justified without reference to the environment; the environment change
  adopts it in the environment's files. Do not ship them as one blended edit.
- Lessons from one environment reach the harness only as generic design guidance
  (`skills/environments/references/design.md`), never as that environment's specifics.
- If you cannot tell which layer a change belongs to, stop and ask. Default to the
  environment layer.
- In the PR description, classify each changed file as environment or harness, and confirm
  that no harness file mentions a specific environment.

## Repository

- The repo is nicolasakf/prime-env-harness; development happens on the `main` branch.
- PRs go to this repo with base `main`:
  `gh pr create --repo nicolasakf/prime-env-harness --base main`.
- CI: `ci.yml` (fmt, clippy, sharded tests) and `environments.yml` (Docker integration, dependency
  audit) on `main` pushes and PRs; `release.yml` on version tags.

## Relationship to Prime Agent

- Prime Env Harness is an independent project. It started from Prime Agent's Rust workspace
  (revision `3358e0016bce7cf34a195af58bbd91a26e17d694`) and no longer tracks it.
- We owe Prime Agent and Prime Intellect credit (README, LICENSE, citation) but not
  compatibility: no TypeScript-parity gate, no obligation to keep upstream's contracts,
  and no need to keep merges with upstream conflict-free.
- The `upstream` git remote exists only so we can read Prime Agent's development and
  pull in what we want, when we want, by cherry-pick or ad hoc merge. There is no sync
  schedule. When you port an upstream change, adapt it to this repo's rules and name the
  upstream commit in the commit message.
- Inherited behavior is ours to change. Do it deliberately: describe the change in the PR,
  and keep the inherited surface contract below accurate rather than treating it as frozen.
- Do not edit or depend on a Prime Agent checkout or installation. Prime Env Harness state, updates,
  and release channels are separate from Prime Agent's.

## Style and structure

- Workspace crates are prefixed `pa-`. The hard ownership rules: one owned area per crate,
  pa-types is the only shared crate, cycle-free dependency direction, minimal public APIs,
  no god-modules. The dependency direction is pinned in the Crates table below; each crate's
  README.md states its scope, non-goals, and public API surface.
- Prefer private modules with an explicitly exported public crate API. Internals are `pub(crate)`.
- Aim for files under 2,000 lines, tests included. The 2,000-2,100 range is a soft review
  signal, not a merge limit: when adding to an already-large file, consider splitting by
  responsibility rather than growing it further. Move related tests and docs with extracted code.
- Name modules for what they own, not `utils` or `common`. Follow existing structure: in
  `crates/pa-core/src/kernel/manager/`, `mod.rs` connects `execution.rs`, `requests.rs`, and
  `teardown.rs`; put a new kernel-manager concern beside them. In
  `crates/pa-core/src/cron/store/`, `mod.rs` connects `heartbeat.rs`, `jobs.rs`, and
  `session_artifacts.rs`; keep storage work there rather than growing the scheduler.
- Inline format args: always prefer `format!("{x}")` over positional.
- Collapse if statements per clippy::collapsible_if.
- Prefer method references over closures per clippy::redundant_closure_for_method_calls.
- Make `match` statements exhaustive; avoid wildcard arms.
- New traits need doc comments explaining their role and how implementations are expected to behave.
- No opaque positional `bool`/`Option` parameters (`foo(false)` is unreadable). Prefer enums,
  named methods, or newtypes. If you must pass an opaque literal by position, use an exact
  `/*param_name*/` comment matching the callee signature.
- Prefer native RPITIT trait methods with explicit `Send` bounds
  (`fn foo(&self) -> impl Future<Output = T> + Send;`) over `#[async_trait]` or
  `#[allow(async_fn_in_trait)]`. Implementations may use `async fn` when they satisfy the contract.
- No single-use helper methods. Do not create a helper referenced only once.
- Instrument async work at the definition (`#[tracing::instrument(...)]`), not with
  `.instrument(...)` at call sites. Check whether the callee is already instrumented first.

## Change hygiene

- One logical change per PR. Fixes ride with the change that introduced them when possible; a PR
  that mixes a feature with unrelated lint fixes or refactors hides both from review.
- If you change dependencies (`Cargo.toml`), regenerate/commit `Cargo.lock` in the same change.
  A new dependency is an architectural change: state in the PR why the existing crates cannot
  host the functionality, and `make deny` must stay clean for it.
- If a change starts forcing edits across many crate internals, stop and fix the boundary instead.

## Tests

- Prefer whole-object equality comparisons over field-by-field checks.
- Do not add tests for statically defined values.
- Do not add negative tests for logic that was removed.
- Bug fixes need a regression test that fails without the fix.
- Verifiers over self-assessment: tmux user-level tests, golden corpora replayed against real
  captured data, and environment fixtures. No lane merges without its verifier passing, rerun
  by the reviewer where feasible.
- Tests must wait for observable readiness, not fixed sleeps or retry-to-green loops. If a
  test must be disabled, give a reason at the test. Use isolated ports and temporary paths, and
  restore shared state. Run focused tests when changing their behavior.

## Lint discipline

- Zero-warning posture: the merge gates run fmt + clippy + tests at `-D warnings`, so a `warn`
  lint is a merge blocker. Keep the enabled set deliberate and selective; enable a new lint family
  only with every current site fixed in the same change.
- Explain lint exceptions next to the `#[allow(...)]` or workspace configuration; keep
  exceptions narrow. Advisory ignores in `deny.toml` need a reason and review date.

## Development workflow

- During iteration, run focused tests for the changed behavior and scoped clippy when
  needed. Use `cargo check -p <crate>` for a quick compile check. Broaden validation
  when the change affects other crates or a failure reveals a wider concern.
- Launch the development app with `cargo run -p pa-cli --bin prime-env-harness`.
  Edit, exit the app, and rerun that command; Cargo rebuilds changed code automatically.
  Use the debug build for routine manual checks. Release builds belong to final
  validation or work that specifically requires optimized performance.
- Run heavy Cargo commands sequentially. Do not overlap tests, clippy, or builds
  against the same checkout. For lower CPU pressure, use `-j 2` on Cargo commands,
  or `CARGO_BUILD_JOBS=2 make check`; this can increase elapsed time.
- Run `make check` once after a code change is ready for final validation and before
  merge. It includes workspace formatting, clippy, tests, and a release build; do
  not separately repeat those same gates. Rerun checks only when later edits,
  failures, or unresolved concerns require them. Run `make deny` when dependencies
  change, and retain the required environment verifiers.
- Documentation-only changes need a diff and whitespace review, without Rust
  compilation or tests. Report failed or unavailable gates accurately; focused
  checks do not replace the merge requirements.

## Merge gates

- `cargo fmt --all --check`, `cargo clippy --workspace --all-targets -- -D warnings`,
  `cargo test --workspace` must pass before every merge. Run `make check` — the local mirror of
  the same gates; CI runs them in `ci.yml` on `main` pushes and PRs (`release.yml` runs on
  version tags). File size past 2,000 lines is review guidance only and never blocks a merge.
- **User-visible changes need evidence.** Every PR that changes what a user sees or does must
  say so in its description and show it working: a screenshot or frame capture for rendered
  output, a tmux or scripted session for interactive behavior, and a test or captured trace
  for protocol changes. A feature that "works" but was never run end to end does not pass
  review. There is no comparison against the TypeScript Prime Agent binary.
- PRs must state ownership compliance (crate README scope/non-goals/public API, dependency
  direction) and classify the change: internals, new `pub` surface, or a new
  dependency/cross-crate re-export. The latter two are architectural changes — an innocent-looking
  `pub use` is a very simple way to break encapsulation.
- The compiled fallback model catalog `crates/pa-ai/src/models_generated.rs` is
  hand-maintained Rust; edit it by hand (there is no generator). It began as a copy of
  Prime Agent's catalog and is ours to diverge. The catalog fixture `crates/pa-models/tests/fixtures/catalog.v1.json` refreshes with
  `scripts/generate-catalog-fixture.py`. Bulk data files are exempt from the size guidance.

## Adoption telemetry

Every user-visible feature ships its adoption telemetry event in the same PR as the feature:
the event name + properties join the versioned schema (`pa-telemetry`), and a
seam emits it from day one. Telemetry properties never carry prompt, session, or file content
(primitives only; see `pa-telemetry`).

## Branding

The product is Prime Env Harness, an independent project that began from Prime Agent. The README, license, and citation acknowledge
Prime Agent and Prime Intellect on purpose; keep those. Elsewhere, scrub "pi"/"pi-mono"/"pi-ai"/
"Prime Intellect"-style naming from all user-visible surfaces (docs, READMEs,
CLI help text, error messages, splash/onboarding strings, keybinding hints, TUI
labels, and code comments that quote user-facing strings); brand everything
Prime Env Harness. Audit with a repo-wide grep and classify every hit (user-visible
vs wire-internal vs comment) before scrubbing, and list the preserved wire
identifiers in the PR body so the reviewer can verify none were wrongly scrubbed.

EXCEPTION: inherited protocol identifiers (e.g. the PI_PACKAGE_DIR env var, settings keys, provider IDs like prime-inference, harness _meta namespaces like ai.primeintellect.prime-agent, lockfile names) stay as they are until we deliberately rename them. Renaming one is its own logical change that updates every reader and writer and any stored data; do not scrub them incidentally.



## Inherited surface contract

This is the behavior inherited from Prime Agent that Prime Env Harness currently ships. It is not
frozen by upstream; change it deliberately, say so in the PR, and update this list.

- Tools exposed to the model: `bash`, `edit`, `ipython` (internal helpers: `rename`, `stdout`).
- RLM kernel API in the persistent Python REPL: `rlm.spawn/find_models/collect/list_subagents/delete_subagent/create_session/progress_note`, `rlm.harness` CRUD, `agent_message.send`, `agent_observe`, `compact`, `goal`, `refine`, `attach_image`, skills (markdown + Python) per the skill contract in the base system prompt.
- System prompt structure: layered — cache-stable static layer files (core harness description with the full API surface, mandatory usage rules, opinionated guidelines, per-model map) followed by one dynamic tail (packages, project context, skills inventory, MCP servers, environment, session role); the harness digest stays a separate `[harness-digest]` user message. `prime-agent prompt` dumps the assembled prompt with its layer breakdown.
- CLI shape: the inherited `prime-agent` binary's commands and flags, and headless modes (RPC/daemon/session-worker); `prime-env-harness` is the product binary.

## Crates

One owned area per crate; `pa-types` is the only shared vocabulary crate.
Dependencies flow from the composition root toward lower crates, never back upward.
The table summarizes each crate's current direct workspace dependencies:

| Crate | Purpose | Direct workspace dependencies |
| --- | --- | --- |
| `pa-types` | Shared wire and domain types | none |
| `pa-telemetry` | Events and sinks | none |
| `pa-agent` | Provider-independent agent loop | none |
| `pa-ai` | Providers, model registry, streaming | `pa-types` |
| `pa-models` | Live model catalog and transport | `pa-ai`, `pa-types` |
| `pa-core` | Session engine, tools, skills, kernel, settings | `pa-types`, `pa-ai`, `pa-models`, `pa-agent`, `pa-telemetry` |
| `pa-daemon` | Supervisor, workers, wire protocol | `pa-types`, `pa-core`, `pa-agent`, `pa-ai`, `pa-telemetry`, `pa-models` |
| `pa-tui` | Terminal UI, daemon-wire client | `pa-types` |
| `pa-cli` | `prime-agent` binary, composition root | `pa-types`, `pa-core`, `pa-ai`, `pa-agent`, `pa-daemon`, `pa-tui`, `pa-telemetry` |

Layering rules:

- Dependencies only point from higher crates to lower crates shown above. No cycles or
  reverse edges. The leaf crates are peers; add only the dependencies needed for their work.
  Shared wire/domain vocabulary belongs in `pa-types`, not in a higher crate or a duplicate.
- `pa-tui` renders from wire types and events; it does not link the session engine.
- `pa-cli` is a composition root: it wires crates together and contains no business logic.

## Reliability model

- The daemon is a supervisor: it spawns one worker process per active session instead of hosting sessions in-process. Workers are supervised, restarted with backoff, and sessions persist on disk (append-only JSONL, same layout as `~/.prime/agent/sessions`) so reattach works even if the supervisor restarts.
- No stubs, no `todo!()`, no swallowed errors (`anyhow` bubbling to UI is fine).

## References

- Cursor Bugbot's PR review rules (`.cursor/BUGBOT.md`) mirror the standards in this file - update both whenever either changes.
# Project scope

This repository is `nicolasakf/prime-env-harness`, an independent project that began from Prime Agent's
Rust workspace (starting revision `3358e0016bce7cf34a195af58bbd91a26e17d694`). The environment application uses
`prime-env-harness` and `~/.prime-env-harness`; never edit sibling checkouts.
Prime Agent compatibility is not a goal: there is no TypeScript-parity requirement, and the inherited
builder behavior may change deliberately (see "Relationship to Prime Agent"). The environment contract,
participant profile, daemon extension, and `/env` UI are Prime Env Harness's own surfaces. Docker is optional,
including for participant Python.
Product purpose: building environments, running evaluations, and creating benchmarks. Training
(RL, fine-tuning) is out of scope; environments and run records may be adapted for use with
external training tools, but the harness does not implement training.
`pa-environments` owns execution and persistence and depends only on `pa-types`.
`pa-core` and `pa-daemon` may depend on it; `pa-tui` still depends only on shared
wire types. Direct dependencies added by this project use exact versions. Follow the Development workflow above: focused environment tests during iteration,
`make check` for final code validation, and `make deny` when dependencies change. Leave changes uncommitted unless asked.
