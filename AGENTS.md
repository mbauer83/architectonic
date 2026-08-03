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

**This list is CI.** `tests/architecture/test_local_gates_match_ci.py` fails when
`.github/workflows/ci.yml` runs a command this section does not name, so "green locally, red in CI"
cannot be a surprise about *which* commands exist. It went unchecked once and CI caught two real
defects — a coverage floor and an IPv4/IPv6 bind — after a release was tagged.

Run one at a time, never concurrently, before committing:
1. `uv run pytest --tb=short -q` — must be 0 failures, and 0 warnings: `filterwarnings` makes an
   unrecognised warning an error, with each exception narrowed to one message and a reason. Not
   `python -m pytest`: `pyproject.toml` sets `addopts = "-n auto"`, and only `uv run` resolves
   pytest-xdist, so the bare form dies with `error: unrecognized arguments: -n` before running
   anything. `-n auto` is safe at full width now — the PlantUML toolchain is bounded at its one
   acquisition point in `tests/conftest.py`, so the `PYTEST_XDIST_AUTO_NUM_WORKERS=6` prefix this
   list used to carry is no longer needed (and the capped run is the *slower* of the two).
2. `ruff check src/ tests/` — must be 0 errors (including E501)
3. `uv run zuban check` — must pass
4. `uv run tools/openapi/generate_timeout_policy.py --check` — the frontend's committed timeout
   policy still matches the manifest
5. `uv run tools/docs/generate_mcp_docs.py --check` — the generated MCP documentation still matches
   the registered tools
6. `uv run python tools/docs/check_doc_links.py` — documentation links, anchors and media references
7. `uv run tools/ontology/generate_types.py`, then `git diff --exit-code -- tools/gui/src/domain/types.generated.ts`
   — the committed frontend types are the ontology's current output
8. `uv run python -m src.infrastructure.rendering.generate_static_includes engagements/ENG-ARCH-REPO/architecture-repository --check`
   — the generated diagram include files still match the ontology
9. `uv run python tools/licensing/check_licenses.py --ecosystem python --check`, the same with
   `--ecosystem npm`, and `uv run python tools/licensing/generate_notices.py --check` — no denied,
   unknown or unacknowledged licence, and `THIRD-PARTY-NOTICES.md` regenerates identically

CI enforces the backend coverage ratchet over the *combined* shards (`coverage report`), which a
single local run already satisfies because it covers everything at once.

For any change touching the GUI, its API payloads, or model content the GUI renders, add from `tools/gui/`:

10. `npm run typecheck` and `npm run build`
11. `npm run test:coverage` — **not** `npm test`. Both run the same 1600 tests; only this one applies
    the per-directory thresholds in `vite.config.ts`, which is what CI runs. Running the bare form is
    how a `src/domain/**` floor breach reached CI after the tag: six type-level `*.test-d.ts` contract
    files counted as 0%-covered source and took the directory from ~90% to 71.9%.
12. `npm run contracts:check` — the committed `openapi.generated.ts` matches the backend, and the
    hand-written effect schemas match it. Self-contained: it builds the application in-process, so it
    needs no running backend and writes nothing. When it reports staleness, run
    `npm run contracts:generate` and commit the result.
13. `npm run test:e2e` — run `npm run build` first: the default base URL is `http://localhost:8000`,
    where `arch-backend` serves the built SPA, which is what CI drives and what ships. Pass
    `E2E_BASE_URL=http://localhost:5173` to iterate against a Vite dev server instead.
14. `npm run lint` — read the output in full; never pipe it through `tail` or `grep`, which masks the
    exit code. It takes ~10 minutes; run `npm run lint:fast` while iterating and the full one once at
    the end. CI passes `-- --concurrency auto`, which changes only how long it takes.

The browser suite is the only one that exercises the real application, so leaving it to CI means UI and content regressions are discovered after the fact rather than before the commit.

## Commit messages

**`Area: clause`, where the clause completes "When applied, this commit will …".**

```
Quality: empty the operation register — 38 assurance operations requested
REST: stop operations that return bytes advertising JSON
Assurance: refuse to delete a node another analysis references
```

- **One area, from the vocabulary below.** Pick an existing name rather than coining a synonym;
  a second word for the same concern makes the history unsearchable, which is the only thing the
  prefix is for.
- **Imperative, lowercase after the colon** — identifiers and numbers keep their own form, so a
  clause may open `` `--help` `` or `404`. "REST: typed contracts for the platform reads" is a
  label; "REST: type the contracts for the platform reads" says what applying it does.
- **One concern per commit.** Where a commit genuinely carries two, lead with the more prominent
  and name the second after a semicolon, with its own area:
  `Index: add the close() it never had; Model: withdraw a requirement pagination made impossible`.
  Three areas means it should have been two commits.
- **The body says why**, and quotes the numbers a register moved by. The subject says what.

**The vocabulary.** Layers and long-lived concerns, not a taxonomy to be extended per change:

| Area | Covers |
| --- | --- |
| `REST` | the HTTP surface: routers, response contracts, the served OpenAPI document |
| `Manifest` | the route-policy manifest itself, as distinct from what it governs |
| `GUI` | `tools/gui/` — views, client, generated types, browser suite |
| `MCP` | the MCP tool mounts and what they answer |
| `Assurance` | the confidential store and the STPA/CAST/GRC/GSN/security surfaces |
| `Backend` | the `arch-backend` process: startup, shutdown, runtime catalogs |
| `Viewpoints` | viewpoint execution and authoring |
| `Diagram types` | the diagram-type and datatype catalogues |
| `Groups` | the group lifecycle |
| `Sync` | diagram synchronisation |
| `Index` | the artifact index |
| `Domain` | `src/domain/` — the ontology and its projections |
| `Write` | the write path and its refusal vocabulary |
| `Quality` | gates, fixtures, walks, and the shrink-only registers |
| `Docs` | `docs/`, `README.md`, `CHANGELOG.md` and its assets |
| `Model` | repository content: entities, connections, requirements, verifiers |
| `Tooling` | `tools/` other than the GUI |
| `Consolidation` | removing a duplication that spans layers, so no single layer owns it |
| `Release` | the version bump and what advertises it |

`tests/architecture/test_commit_message_convention.py` holds the shape and the vocabulary. It exists
because the convention silently lapsed for 81 consecutive commits: a rule with no gate reads as
optional to whoever arrives next.

## REST routes and response contracts

Every REST operation has exactly one row in the route-policy manifest
(`src/infrastructure/rest/route_policy/`), and that row — not the decorator — is what the fitness
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
