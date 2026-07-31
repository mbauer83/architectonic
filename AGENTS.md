# Agent Instructions

Conventions and gates for ALL coding agents working in this repository (`CLAUDE.md` is a
symlink here). Humans: start with `CONTRIBUTING.md`, which these rules complement.

## Coding guidelines and style

On any coding or code-review task, if the `arch-repo-read` MCP server is available, query it for coding guidelines, best practices, and style guides before writing or reviewing code. Read any matching documents in full and apply them. Search with terms like "coding guidelines", "best practices", "style guide", "conventions".

## Architectural discipline

**Always choose the principled solution, never a workaround.**

When something is missing from a class or interface, add it at the correct layer. Do not route around the gap using a different, less appropriate API.

Examples of workarounds to reject:
- A facade is missing a delegation method → do not reach through to the underlying store using a different, less efficient call; add the delegation.
- A protocol/port declares a method the implementing class lacks → implement it; don't call an alternative that happens to return equivalent data.
- A test setup is brittle because the production code has an incomplete contract → fix the contract, then write the test against it.

After every such fix: add a unit test verifying the delegation, and a regression test reproducing the original failure scenario.

## Quality gates (every change)

Run one at a time, never concurrently, before committing:
1. `uv run pytest --tb=short -q` — must be 0 failures. Not `python -m pytest`: `pyproject.toml`
   sets `addopts = "-n auto"`, and only `uv run` resolves pytest-xdist, so the bare form dies
   with `error: unrecognized arguments: -n` before running anything.
2. `ruff check src/ tests/` — must be 0 errors (including E501)
3. `uv run zuban check` — must pass
4. `uv run tools/openapi/generate_timeout_policy.py --check` — the frontend's committed timeout
   policy still matches the manifest

For any change touching the GUI, its API payloads, or model content the GUI renders, add from `tools/gui/`:

5. `npm run typecheck`, `npm test`, `npm run build`
6. `npm run contracts:check` — the committed `openapi.generated.ts` matches the backend, and the
   hand-written effect schemas match it. Self-contained: it builds the application in-process, so it
   needs no running backend and writes nothing. When it reports staleness, run
   `npm run contracts:generate` and commit the result.
7. `npm run test:e2e` — needs the backend running on `:8000`; pass `E2E_BASE_URL` if it is elsewhere
8. `npm run lint` — read the output in full; never pipe it through `tail` or `grep`, which masks the
   exit code. It takes ~10 minutes; run `npm run lint:fast` while iterating and the full one once at
   the end.

The browser suite is the only one that exercises the real application, so leaving it to CI means UI and content regressions are discovered after the fact rather than before the commit.

## REST routes and response contracts

Every REST operation has exactly one row in the route-policy manifest
(`src/infrastructure/gui/route_policy/`), and that row — not the decorator — is what the fitness
functions in `tests/architecture/` compare the served surface against. Adding or renaming an
operation means editing the row, and a handler that names an operation id the manifest does not
declare fails its request rather than only a test.

A rename moves its decorator, its manifest row, its `authorized_write` key, its cache-eligibility
template and its client/proxy timeout rule **in the same commit**. The migration ledger in
`route_policy/_pending.py` records what is still served at its old address and what is not served
yet; both shrink to empty, and nothing may be added to either.

## Test assertions against live model content

Tests that read the real repository or the real assurance store must never assert an exact count,
an exact list, or a fixed position derived from that content. Authoring an entity, a connection, or
a guidance layer is the product working; a test that fails because of it is reporting a false
regression, and the failure surfaces far from the change that caused it.

Assert the invariant the count was standing in for instead:
- a neighbourhood is non-empty, and expansion adds to it — not that it holds four nodes
- a level appears exactly once, and every entry is labelled and non-empty — not that there is one entry
- a specific expected item is present — not that it is the third row

Exact counts are fine against fixtures the test itself creates, where the test owns the content.

## Model authoring

All model writes go through MCP tools (`artifact_create_entity`, `artifact_add_connection`, etc.). Never edit model files by hand. If a tool is wrong, fix the tool.
