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
for good. A rolling `exclude-newer` in `[tool.uv]` would do the opposite — uv resolves it
to a moving timestamp, so every `uv sync` re-resolves and rewrites the committed lock.

So pass the window on the commands that *change* the lock, and nowhere else:

```bash
uv lock --exclude-newer "24 hours"
uv lock --upgrade --exclude-newer "24 hours"
uv add <package> --exclude-newer "24 hours"
```

npm has its own resolution-time floor in `tools/gui/.npmrc`, and `npm ci` installs from the
lock without resolving, so nothing extra is needed there.

After any npm re-lock, refresh the publish-time evidence the age gate reads and commit it:

```bash
uv run tools/supplychain/check_supply_chain.py --ecosystem npm --write
```

`uv.lock` records an upload time on every artifact it pins, so the Python half needs no
such file and no registry call.
