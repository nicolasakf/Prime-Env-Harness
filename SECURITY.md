# Security policy

## Reporting a vulnerability

Please report security issues privately, not in a public issue. Use GitHub's
**Report a vulnerability** button on this repository's Security tab
(Security → Advisories → Report a vulnerability). Include what you found, how to
reproduce it, and the version or commit you tested.

You should get an acknowledgement within a few days. Please give us time to fix the
issue before disclosing it publicly.

## Scope and expectations

Prime Env Harness runs model-generated and environment-supplied code with your user
permissions.

- **Local execution is not a sandbox.** Use the Docker backend, and grant networking,
  mounts, secrets, and integrations only when an environment needs them.
- Execution policy, private-information handling between seats, and the immutability
  of saved environment versions are security-relevant. Bugs that let one participant
  see another's private information, or let an environment exceed its granted policy,
  are in scope.
- Dependency advisories are tracked with `make deny`. Known exceptions are listed,
  with reasons and review dates, in [deny.toml](deny.toml).

Only the latest release and `main` are supported.
