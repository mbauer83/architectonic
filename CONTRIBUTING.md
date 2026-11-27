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

Every pin must be at least 24 hours old and free of known vulnerabilities.
`uv run tools/supplychain/check_supply_chain.py --ecosystem {python,npm} --check` audits
both ecosystems for vulnerabilities and checks the age of every entry in `uv.lock`.

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

npm needs none of this, because it has the setting uv lacks. `tools/gui/.npmrc` sets
`min-release-age=1`, which makes npm refuse to build a tree from a version published in the
last day — at resolution, which is the only moment a young version could enter the lock. It
writes nothing into `package-lock.json`, and `npm ci` installs from the lock without
resolving at all, so there is nothing to re-check afterwards.

When the two controls conflict — the only fix for a known vulnerability is younger than
the floor — the way through is a dated entry in
`tools/supplychain/emergency_exceptions.py`, naming one package at one version with a
justification and the day it stops applying. It refuses to be constructed without those,
it admits nothing after that day, and it fails the gate until it is removed.

## Cutting a release

A release is a signed tag `v<version>` on a commit whose `pyproject.toml` declares that version and
which carries `changelog-assets/<version>-detail.md`. Pushing the tag starts
`.github/workflows/release.yml`, which runs in this order:

1. **CI on the tagged commit.** When `main` was pushed with the tagged commit, the CI run that push
   started is the verdict: the release waits for it if it is still running and uses its result.
   Only a run of `ci.yml` triggered by a push to `main` for exactly this commit counts. Without a
   passing one, the release workflow runs `ci.yml` on the tag itself. Push `main`, then the tag, and
   CI runs once per release.
2. **Publish**, only when that CI passed: the GUI is built, bundled and given a `SHA256SUMS`
   line, both files receive a build-provenance attestation, and the GitHub release is created with
   the detail file as its notes.

A tag on a commit whose CI fails publishes nothing. Fix the defect on `main`, then move the tag to
the fixed commit or cut the next patch version; `arch-update` installs only published releases, so
an unpublished tag reaches no installation.

The tag must be signed by a key listed in `.github/release-signers` of the version installations
already run; a new key ships in a release before any tag is signed with it.
