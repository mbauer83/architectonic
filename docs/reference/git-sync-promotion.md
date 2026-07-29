# Git Sync & Promotion

Architecture changes accumulate as file edits, then reach git in two explicit steps: *saving*
(committing locally) and, for enterprise changes, *submitting for review* (pushing a branch).
Promotion moves selected content from an engagement repo up to the enterprise baseline.

&nbsp;

## Promotion

Promotion is a one-way transfer of an explicitly selected set of entities and connections from
engagement to enterprise.

- **Conflict detection** matches by both `(artifact_type, normalized_name)` and
  `(artifact_type, id_suffix)`. The same entity renamed in one repo is caught by the ID match;
  the same name with a different ID is caught by the name match.
- **Resolution strategies** — accept engagement version, accept enterprise version, or manual
  merge.
- **Blocked** when the engagement repo's schemata are not supersets of the enterprise schemata
  (per-violation error) — covers attribute/frontmatter/document schemas, and, for a promoted
  entity or connection carrying a specialization, the specialization itself plus its attached
  profile (inline attributes or attachment schema file): a specialization declared only in the
  engagement repo's own `.arch-repo/specializations.yaml` (not shipped by the ontology module
  and not also declared in the enterprise repo) blocks promotion with an actionable message.
- **Blocked** when a promoted diagram or matrix carries a `viewpoint:` application referencing
  an engagement-only [viewpoint](../03-modeling/viewpoints.md) definition: the definition, at
  the exact pinned version, must be promoted alongside it. The match is **exact-version** — a
  newer enterprise definition does not by itself satisfy an older engagement pin; re-pinning to
  the enterprise version is a separate, explicit promotion step. A promoted viewpoint
  definition is itself validated transitively (its own scope/query attribute references must
  resolve in the enterprise repo).
- **Asymmetric references** — enterprise entities may reference only enterprise entities;
  engagement entities may reference both. The verifier enforces this.

Run promotion through the `↑ Promote` GUI view, the `artifact_promote_to_enterprise` MCP tool,
or REST.

&nbsp;

## Saving — engagement

| Surface | How |
|---|---|
| GUI | "Save Changes" → commit message; optional immediate push |
| MCP | `artifact_save_changes(message="…", target="engagement")` |
| REST | `POST /api/sync/engagement/save` `{"message": "…", "push": true}` |

With `push=true` (default) the commit is pushed to the remote branch immediately.

&nbsp;

## Enterprise — branch-based review workflow

Enterprise changes follow a three-step lifecycle that works with any git host without API
integration:

```
 promote artifacts ──► save (commit) ──► submit for review (push branch → open PR manually)
   [accumulating]        [accumulating]         [pending]
                                                   │
                              [synced] ◄───────────┘  auto-detected when the branch
                                                       content lands in origin/main
```

- **Accumulating** — the first enterprise write creates an isolated working branch (e.g.
  `arch/work-20260425-143012`); later promotions accumulate on it. The enterprise read view
  always reflects branch content.
- **Saving** — commits the working branch without pushing
  (`artifact_save_changes(target="enterprise")` / `POST /api/sync/enterprise/save`). Save
  commits (engagement and enterprise) run the artifact verifier over the whole working tree
  first — a tree holding a malformed manual edit rejects the save with no commit and no
  state change. Submit's push and Discard's branch cleanup are the content-neutral
  exceptions: they introduce no artifact content and skip verification.
- **Submitting** — pushes with upstream tracking and marks pending; the returned branch name
  is used to open a PR (`artifact_submit_for_review()` / `POST /api/sync/enterprise/submit`).
- **Auto-merge detection** — the sync loop polls `origin/main`; when the branch content is
  detected there (content diff, so squash/rebase merges are handled), it checks out `main`,
  pulls, and transitions to *synced*.
- **Discarding** — `artifact_withdraw_changes(confirm=True)` /
  `POST /api/sync/enterprise/withdraw`. Discard requires a clean tree and rejects when there
  is nothing to discard (never a silent success). A pending discard is an idempotent
  desired-state transition — remote ref deleted, checkout `main`, local branch deleted,
  state cleared — where every already-satisfied step counts as success, so a retry after a
  partial failure converges.

The workflow controls live in the header's **Changes** menu next to the repository status
chip; each action appears exactly when the sync lifecycle offers it AND the backend's
per-intent authority allows it (a fetch/upstream fault still allows the local Save that
resolves a dirty tree while denying promotion, Submit, and remote-touching Discard).

State is persisted in `.arch/enterprise-sync.json` (versioned, with a typed sync-health
overlay) and survives restarts.

&nbsp;

## Continuous git sync

When a repo is configured as a git repo, the backend runs a background sync loop (default 60s).

**Engagement** — fetch every cycle; `git pull --ff-only` when clean and behind;
`git pull --rebase` when there are local commits; abort cleanly and emit a conflict event on a
rebase conflict.

**Enterprise** — *synced*: fetch + fast-forward; *accumulating*: fetch only, emit a divergence
event if `origin/main` moved ahead; *pending*: fetch + content-diff to detect a merge, then
transition to *synced*.

In all cases writes are briefly blocked during pull/checkout, the block auto-lifts after 60s
if a sync fails, and the artifact index refreshes (and the GUI is notified via SSE) after any
pull or transition.

&nbsp;

## Git authentication

SSH and HTTPS remotes are both supported. Credentials are never written to disk — they are
held in process memory and injected into git subprocesses via a temporary askpass helper.

`arch-backend` and `arch-init` probe configured remotes and prompt on the terminal only when
credentials are required. For `--daemon`, prompting happens in the foreground parent before
the daemon forks. For CI / non-interactive use, set environment variables to skip prompting:

```bash
export ARCH_GIT_SSH_PASSWORD="my passphrase"   # SSH key passphrase
export ARCH_GIT_HTTPS_TOKEN="ghp_…"             # personal access token (no username needed)
# …or an explicit username + password/token instead (takes precedence over the token):
export ARCH_GIT_HTTPS_USERNAME="my-user"        # HTTPS username
export ARCH_GIT_HTTPS_PASSWORD="my-token"       # HTTPS password or token
```

`ARCH_GIT_HTTPS_TOKEN` is the simplest option for GitHub/GitLab, which ignore the username
for token auth; the same variable works identically for `arch-backend`, `arch-init`, and the
container entrypoint, since they share one credential-resolution layer.

To keep the token out of the environment entirely, put it in a file and reference the path
— via `ARCH_GIT_HTTPS_TOKEN_FILE` or the CLI flag (a path, never the token value itself):

```bash
uv run arch-backend --daemon --git-token-file /run/secrets/git_pat
uv run arch-init    --git-token-file /run/secrets/git_pat
```

A daemon started this way inherits only the file *path*, then re-reads the file itself.

> A PAT only authenticates `https://` remotes. SSH remotes use a key pair; the SSH-side
> secret is the key passphrase (`ARCH_GIT_SSH_PASSWORD`), not a token.
