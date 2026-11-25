# Updating an installation

`arch-update` brings an installation to a published release. Run without flags it is a dry run: it
reads the release record, verifies the release, rehearses the next version's data upgrade against
this deployment and prints what an update would do. With `--commit` it performs that plan and, if
anything fails, puts the deployment back the way it was.

```bash
uv run arch-update                    # check, verify, rehearse, print the plan — writes nothing
uv run arch-update --json             # the same, as a report
uv run arch-update --commit           # perform the update
uv run arch-update --status           # the update in flight, or the last one
uv run arch-update --rollback         # put an update in flight back
```

The first release that carries `arch-update` is installed by hand (pull, `uv sync`, rebuild the GUI,
`arch-repair upgrade --commit` with the backend stopped). Every release after it is installed with
this command.

An installation on 0.11.x updates to 0.12.0 with 0.11.x's `arch-update`, which still refuses edited
configuration files. Follow [Updating from 0.11.x](upgrade-guide.md#updating-from-011x) for that one
step.

&nbsp;

## What the dry run checks

| Line | What it says |
|---|---|
| `installed` | the version the checkout declares, the deployment kind, whether the backend serves and how, whether the assurance store is open, the branch and commit, and whether tracked files are modified |
| `release` | the newest published release (or the one named with `--to`), its tag and commit, whether the tag's signature verifies against the signers this installation trusts, and whether the release's commit is the commit the tag names on the origin |
| `assets` | each downloaded asset against the digest the release states and the digest in `SHA256SUMS` |
| `provenance` | whether the build-provenance attestation was verified (not yet in this version) |
| `rehearsal` | the release's own `arch-repair upgrade` dry run over this deployment's repositories and operational targets, run in a throwaway worktree: how many findings apply automatically, how many block, how many targets could not be inspected |
| `not applied` | an enterprise tier the migration leaves at its older format because this deployment does not administer it, with the number of pending findings and how its maintainer applies them |
| `plan` | the steps `--commit` would take, in order |
| `will ask for` | each credential the restart needs and the environment variable that answers it without a prompt |
| `refused` | why the update would not run, and what resolves it |

Signature enforcement follows the installed version: an installation without
`.github/release-signers` cannot say who may sign and reports the signature as not enforced. Once
the file is present, an unsigned tag or one signed by a key it does not list is refused.

The rehearsal costs about half a minute. `--no-rehearse` skips it; the plan then says the live
migration is the first attempt.

&nbsp;

## What `--commit` does

The update is a sequence of phases, each recorded in `.arch/update/journal.json` before it begins
and after it completes. The installed version runs the first three, then hands over to the new one.

1. **Ask for credentials.** A git passphrase the restarted backend will need, or the assurance
   vault's master password where the store is open under the manual activation policy and the key
   is not readable without one. Asked before anything stops; without a terminal, an unanswered
   question refuses the update and names the variable to set.
2. **Stop the backend**, when one serves this workspace. A backend serving in the foreground of a
   terminal is not stopped: the update is refused and names the pid.
3. **Move the checkout** to the release tag by fast-forward on `main`, or detached on another branch,
   keeping the edits to your configuration files (see [Your configuration](#your-configuration)).
4. **Sync the environment** with `uv sync --frozen` and the groups and extras the installed
   environment had. The process then re-executes itself as the new version.
5. **Install the GUI** from the release's bundle, kept beside the previous one until verified. Where
   a release carries no bundle and `npm` is on `PATH`, the GUI is built locally.
6. **Re-provision pinned assets** (`plantuml.jar`, the embedding model) where their pins moved.
7. **Migrate** with `arch-repair upgrade --commit`, which takes its safety point first (see
   [the upgrade guide](upgrade-guide.md#the-safety-point-a-commit-leaves-behind)). Where the backend
   serves with `--admin-mode`, the migration runs with `--admin-mode` too and upgrades the enterprise
   tier as well.
8. **Start the backend** detached on the same port with the same flags.
9. **Authorize the store** where it was open under the manual policy.
10. **Verify** that the checkout declares the release and the backend serves it.

A failure in any phase rolls back: the backend the update started is stopped, the data upgrade's
checkpoint set restored, the previous GUI swapped back, the checkout returned to the recorded commit,
the environment synced to it, the previous pins re-provisioned, the previous backend started and the
store re-authorized. Every reversal is attempted even when an earlier one fails, and what could not
be put back is listed.

The migrated model files appear as changes in a repository that lives inside the checkout, as the
development layout has it; commit them as you would any model change.

The closing `safety` line is the command that returns every target to the state before the
migration, with this deployment's `--workspace` and `--settings` already filled in. Stop the backend
before running it. It refuses while files have changed since the update and lists them; add
`--discard-later-work` once what you need from them is saved.

&nbsp;

## Your configuration

Two tracked files are this installation's configuration rather than software:
`arch-workspace.yaml` (the repositories, the backend port) and `config/settings.yaml` (written by
`arch-assurance init` and `use-backend`, and edited by hand). Leave your edits to them uncommitted.

- The dry run reports them as kept, and they do not count as a modified checkout.
- A release that leaves the file unchanged moves underneath your edits.
- A release that changes the file has your edits merged onto its version. When the two touch the
  same lines, the dry run refuses and names the file; `git diff HEAD <tag> -- <file>` shows the
  release's change.
- A file marked `git update-index --skip-worktree` or `--assume-unchanged` hides its edits, so the
  dry run refuses until the flag is cleared.

Commits of your own on `main` stop a fast-forward. The dry run refuses with the commit `main` and
the release share: `git reset --mixed <that commit>` turns configuration commits back into
uncommitted edits. Other work belongs on a branch of its own.

&nbsp;

## Exit codes

| Exit | Meaning |
|---|---|
| `0` | dry run finished, or the update is complete and verified, or the installation is already at the newest release |
| `3` | blocked: nothing was installed, or everything was put back |
| `20` | partial: a phase failed and the rollback could not undo everything; the report lists what remains |
| `21` | infrastructure failure before anything changed: the release source, a digest, a refused signature, a missing credential without a terminal, or another update already in flight |

&nbsp;

## Deployment kinds

The kind is observed, never configured.

| Kind | How it is recognised | Behaviour |
|---|---|---|
| local checkout | a `.git` directory, `uv` on `PATH`, no compose project running from this checkout | the phases above |
| compose host | the checkout's compose project runs the `app` service | see below |
| container | no `.git`, or `/.dockerenv` | the dry run reports; `--commit` is refused with the host-side command |
| remote-attached | `ARCH_MCP_BACKEND_URL` names a backend this checkout does not run | the dry run reports the remote's version; `--commit` is refused |

A checkout that both serves a local backend and runs the compose project is refused until
`--deployment local` or `--deployment compose` says which is meant.

**Compose host.** The image is built for the new checkout while the old container keeps serving;
the image it replaces is kept as `architectonic:<installed version>`. The container is then stopped
*before* the migration, because the data upgrade's backend-not-serving guard probes `localhost` and
cannot see a container serving the same volumes. The migration and, on failure, its `--restore` run
inside the new image with `docker compose run`, against the mounted volumes and with the same
`--settings` and `--workspace` the entrypoint uses. `docker compose up -d` then starts the new
container, and the served version is verified on the published port. A rollback retags the kept
image onto the compose tag instead of rebuilding. Credentials come from `.env`; nothing is
prompted. Use `--compose-file` when the project is not `docker-compose.yml`.

&nbsp;

## Settings

| Key | Default | Meaning |
|---|---|---|
| `update.repository` | `mbauer83/architectonic` | the GitHub repository whose releases are read; `--repository` overrides it for one run |

A `GITHUB_TOKEN` in the environment is sent with release requests, which lifts the anonymous rate
limit.

&nbsp;

## An update in flight

`arch-update --status` shows the journal: the versions involved, the phase last completed, and
whether the new version has taken over. `arch-update --resume` continues an update whose process
was interrupted after the handover; `arch-update --rollback` reverses it. Finished updates are kept
under `.arch/update/history/` with their outcome.

MCP stdio bridges that agent clients started keep running the previous version until the client
restarts them.

---

*See also: [Upgrading a deployment](upgrade-guide.md) · [CLI & backend](cli-and-backend.md) ·
[Docker Compose deployment](docker-compose.md)*
