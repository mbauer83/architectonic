# Architecture Glossary

Canonical vocabulary for the hexagonal architecture of this codebase. Terms are
listed in dependency order (lower entries depend only on earlier ones).

---

&nbsp;

## Module Catalog

**What it is:** The immutable registry of all installed diagram-type modules (C4,
ArchiMate 4.0, …) and the ontology/connection-type data they contribute.

**Key types:**
- `src/domain/modules/module_catalog.py` — `ModuleCatalog` (built by `ModuleCatalogBuilder`)
  records module identifiers, classes, and per-module metadata.
- `src/domain/modules/catalogs.py` — `OntologyCatalog`, `ConnectionSemantics`,
  `DiagramTypeCatalog` expose query methods over the aggregated module data.
- `src/application/derivation/strategy_registry.py` — `DerivationStrategyCatalog`
  records which derivation strategies are registered.
- `src/application/runtime_catalogs.py` — `RuntimeCatalogs` bundles all four
  catalogs into one frozen dataclass injected at every composition root.

**In the self-model:** the matching entity is "Module Catalog"
(`APP@1712870400.yNhgdh.module-catalog`), aligned with the code's canonical name
`ModuleCatalog`.

---

&nbsp;

## Artifact Index

**What it is:** The in-memory, SQLite-backed read model that tracks all parsed
artifacts in the mounted repositories. It answers queries (lookup, search, graph
traversal) and is updated incrementally as files change.

**Key types:**
- `src/infrastructure/artifact_index/service.py` — `ArtifactIndex` implements
  `ArtifactStorePort` (which composes `ArtifactLookup`, `ArtifactSearch`,
  `RelationshipGraph`, `RepositoryScopeResolver`, `ArtifactIndexLifecycle`,
  `ArtifactMutationObserver`).
- `src/application/ports.py` — declares the six narrow store protocols that
  consumers depend on rather than the composite port directly.

**Distinguished from:** the Artifact Repository (the on-disk files). The index is
a derived cache; the repository is the source of truth.

---

&nbsp;

## Artifact Repository

**What it is:** The on-disk storage layer — the git directory tree containing
model files (`*.yaml` entities, `*.puml` diagrams, `*.md` documents). One or more
repositories may be mounted simultaneously as `RepoMount` instances.

**Key types:**
- `src/domain/ontology_representation/artifact_types.py` — `RepoMount` describes a single mount point
  (path + role: engagement or enterprise).
- `src/application/ports.py` — `RepositoryScopeResolver` port resolves scope
  (domain, subdomain) within a repository.

**Distinguished from:** the Artifact Index. The repository is the authoritative
store; the index is rebuilt from it.

---

&nbsp;

## Application Composition Root

**What it is:** The site where all domain modules are registered, `RuntimeCatalogs`
is built, adapters are bound to ports, and the resulting objects are injected into
consumers. No consumer may reach a global singleton; all domain objects flow
downward from here.

**Key files:**
- `src/infrastructure/app_bootstrap.py` — builds `ModuleCatalog`, all catalogs,
  and installs `RuntimeCatalogs` on FastAPI app-state via `Depends`.
- `src/infrastructure/cli/artifact_query_cli.py::main()` and
  `src/infrastructure/cli/arch_assurance.py::main()` — CLI composition roots that
  call `build_runtime_catalogs(get_module_registry())` eagerly before dispatch.
- `src/infrastructure/mcp/artifact_mcp/context.py` — MCP composition root; builds
  catalogs once via `@lru_cache` at the first MCP request.

---

&nbsp;

## Runtime Host

**What it is:** A deployable process that owns exactly one composition root and
presents the application capabilities over a specific transport.

**Three hosts:**
- **HTTP server** — `src/infrastructure/backend/arch_backend_app.py`; FastAPI app
  served by Uvicorn.
- **CLI** — `src/infrastructure/cli/artifact_query_cli.py` and
  `src/infrastructure/cli/arch_assurance.py`; one-shot command processes.
- **MCP server** — `src/infrastructure/mcp/mcp_artifact_server.py`; long-running
  MCP tool host used by Claude Code.

---

&nbsp;

## Scratchpad Aggregate

**What it is:** The preliminary tier: a canvas of untyped **notes**, the **links** drawn
between them, the labelled **areas** (frames) they sit in, and the **groups** clustering
them. The scratchpad is the aggregate root — notes, links, areas and groups have no life
outside one, which is what lets a note be created from nothing but a title: its id is
unique within its scratchpad and meaningless outside, so no global namespace has to accept
it.

**Key types:**
- `src/domain/scratchpad/scratchpad.py` — `Scratchpad` (root), `Note`, `Link`, `Area`,
  `Group`, `Layout`, `ModelRef`; every invariant is enforced here and nowhere else.
- `src/domain/scratchpad/geometry.py` — `Point`, `Rect`, and the 5-px grid every stored
  coordinate is snapped to.
- `src/application/scratchpad/document.py` — the single mapping between the aggregate and
  its document form, shared by the YAML file and the REST payload.
- `src/application/scratchpad/service.py` — `ScratchpadService`, the one door both the REST
  router and the MCP tools go through.

**Vocabulary:**
- **area membership** is *spatial and derived* — the frame containing a note decides which
  area it is in; a note in no frame is `unfiled`, which is legitimate.
- **binding** holds a `model_ref` to content that already exists (type read from the
  entity); **realization** holds one created by a lift (type chosen on the note, then
  frozen). One field with a flag, because the difference is provenance.
- **lifting** turns a selection into ordinary model content through the same verified write
  path as any other authoring. It is one-way: a scratchpad never writes back, and a second
  lift skips what is already realized.

**Distinguished from:** a **document** (prose with prescribed sections) and a **diagram**
(a picture of model content). A scratchpad is a graph with geometry whose contents are not
model content until lifted.

---

&nbsp;

## Verification Policy

**What it is:** The set of rules that `ArtifactVerifier` enforces, expressed as
pure functions over parsed inputs. Policy is declared at construction time via
constructor flags (`check_puml_syntax: bool`) and the injected `RuntimeCatalogs`.
Policy never touches I/O directly.

**Key files:**
- `src/application/verification/artifact_verifier.py` — `ArtifactVerifier` is the
  policy object; its `verify_*` methods compose the rule functions.
- `src/application/verification/_verifier_rules_*.py` — pure rule functions that
  accept parsed frontmatter/PUML/catalog data and return `list[Issue]`.

---

&nbsp;

## Verification Executor

**What it is:** The I/O machinery that dispatches verification tasks to workers,
checks PlantUML syntax via Java, traverses the filesystem, and persists incremental
state between runs. The executor is an infrastructure concern; it never contains
policy logic.

**Key types:**
- `src/application/verification/verifier_ports.py` — `VerifierScheduler`,
  `PumlSyntaxPort`, `FileInventoryPort`, `IncrementalStatePort` define what the
  verifier orchestration needs from its environment.
- `src/application/verification/_verifier_stdlib_adapters.py` — stdlib-only
  implementations: `ThreadPoolVerifierScheduler`, `FilesystemInventoryAdapter`,
  `DefaultIncrementalStateAdapter`, `_NullPumlSyntax`.
- `src/infrastructure/verification/adapters.py` — `DefaultPumlSyntaxAdapter` wraps
  the Java/PlantUML subprocess (the only truly infrastructure-bound adapter).
