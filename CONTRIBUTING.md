# Contributing to Prime Env Harness

Thanks for helping. Prime Env Harness builds, runs, and evaluates environments
for humans and AI models. Issues and pull requests belong in this repository
(`nicolasakf/Prime-Env-Harness`), not in Prime Agent's.

## Before you start

- Read [AGENTS.md](AGENTS.md). It is the source of truth for repository rules and
  applies to human and AI contributors alike.
- **Environment vs harness.** Every change belongs to exactly one layer. A change to
  one environment (rules, actions, views, prompts, data, tests) stays in that
  environment's files. A change to the shared runtime, UI, prompts, or docs must be
  environment-independent and must not name a specific environment. If you cannot
  tell which layer a change belongs to, open an issue and ask.
- The project does not train models. RL and fine-tuning support is out of scope;
  environments and run records may be used with external training tools.

## Build and test

```bash
cargo run -p pa-cli --bin prime-env-harness   # debug build, rebuilds on change
cargo test -p <crate> <filter>                # focused tests while iterating
make check                                    # fmt, clippy, tests, release build
make deny                                     # after dependency changes
```

Run heavy Cargo commands one at a time (`-j 2` lowers CPU pressure). Use isolated
ports and temporary paths in tests, and wait for observable readiness instead of
sleeping. Some tests are known to fail on macOS; see
[VERIFICATION.md](VERIFICATION.md).

## Pull requests

- Branch from `main`; open the PR against `main` of this repository.
- One logical change per PR. A bug fix needs a regression test that fails without it.
- If you change dependencies, commit `Cargo.lock` in the same change and keep
  `make deny` clean. State why existing crates cannot host the functionality.
- User-visible changes need evidence in the PR: a screenshot or frame capture, a
  scripted session, or a test or trace for protocol changes.
- In the description, classify each changed file as environment or harness and say
  whether the change is internals, new `pub` surface, or a new dependency.

## Prime Agent

Prime Env Harness started from [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent)
and is now independent. Porting an upstream change is welcome; name the upstream
commit in your commit message and adapt it to this repository's rules.
