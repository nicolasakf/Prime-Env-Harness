## Ownership compliance

<!-- Crate scope/non-goals/public API + dependency direction per AGENTS.md -->

## What changed

## User-visible change evidence

<!-- Per the AGENTS.md merge gates: show user-visible changes working end to end. No Prime Agent / TS comparison is required. -->
- [ ] Rendered output: screenshot or frame capture for every touched surface
- [ ] Interactive behavior: tmux or scripted session showing the changed input handling
- [ ] Protocol changes: a test or captured trace
- [ ] Inherited behavior changed on purpose: said so above

<!-- If a checked box does not apply (pure refactor, docs, internal crate), say why. -->

## Gates

- [ ] cargo fmt --all --check
- [ ] cargo clippy --workspace --all-targets -- -D warnings
- [ ] cargo test --workspace
<!-- Windows-touching PRs: make windows-cross (zero warnings) -->

## Test/e2e evidence
