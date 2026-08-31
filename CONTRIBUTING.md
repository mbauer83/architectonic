# Contributing

Architectonic is a single-maintainer project.

- **Pull requests are not accepted.** GitHub does not allow turning PRs off; any opened
  PR will be closed with a pointer to this file. If you want a change, open an issue —
  a good problem description with reproduction steps is genuinely valuable.
- **Issues are welcome** — bug reports, usability findings, and feature requests. Use
  the issue templates; for bugs, include the backend version (`pyproject.toml`), how
  you deployed (compose / local), and what `/health` reports.
- **Security findings** must not be filed as public issues — see [SECURITY.md](SECURITY.md).
- **Working with a coding agent?** The repository's conventions and quality gates are
  encoded tool-agnostically in [AGENTS.md](AGENTS.md) (`CLAUDE.md` symlinks to it), so an
  agent lands with the same rules a human reads here.

## Changing a dependency

Every pin in a committed lockfile must be at least 24 hours old, and free of known
vulnerabilities. Both are checked by
`uv run tools/supplychain/check_supply_chain.py --ecosystem {python,npm} --check`, over
`uv.lock` and `tools/gui/package-lock.json`.

The floor is enforced as a gate over the lock rather than as a resolver setting, because
"no pin younger than 24 hours" only ever becomes more true: once a lock passes it passes
for good. A resolver setting does the opposite. Measured with uv 0.11.7, both forms of
`exclude-newer` put a moving timestamp into the committed lock — the `[tool.uv]` form makes
every `uv sync` re-resolve, and the command-line form writes an `[options]` block naming
the moment it ran, after which `uv sync --locked` fails until someone repeats the flag.

So **re-lock plainly**, and let the gate decide:

```bash
uv lock                                # or --upgrade-package <name> ... for a chosen set
uv add <package>
uv run tools/supplychain/check_supply_chain.py --ecosystem python --check
```

If the gate refuses a pin for its age, wait for it to age or take an emergency exception —
the answer is not to make the resolver keep a date.

npm's floor is different in kind and does belong at resolution time: `tools/gui/.npmrc` sets
`min-release-age=1`, npm writes nothing into the lock for it, and `npm ci` installs from the
lock without resolving at all.

After any npm re-lock, refresh the publish-time evidence the age gate reads and commit it:

```bash
uv run tools/supplychain/check_supply_chain.py --ecosystem npm --write
```

`uv.lock` records an upload time on every artifact it pins, so the Python half needs no
such file and no registry call.

When the two controls conflict — the only fix for a known vulnerability is younger than
the floor — the way through is a dated entry in
`tools/supplychain/emergency_exceptions.py`, naming one package at one version with a
justification and the day it stops applying. It refuses to be constructed without those,
it admits nothing after that day, and it fails the gate until it is removed.
