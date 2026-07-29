# Dependency Policy

Enforced by `tests/architecture/test_dependency_policy.py` (AST-based, baseline mode).

---

&nbsp;

## Package roles

| Package | Role | Notes |
|---------|------|-------|
| `src/domain/` | Core domain | Pure business concepts and contracts. No outward dependencies. |
| `src/application/` | Application layer | Orchestrates domain objects and ports. |
| `src/config/` | Configuration leaf | Workspace / repo path resolution; reads YAML. |
| `src/ontologies/*/` | Pure ontology plugins | Provide ArchiMate / SysML data to the registry. |
| `src/diagram_types/*/` | Adapter-plugins | Diagram type descriptors and renderer adapters. |
| `src/infrastructure/` | Infrastructure | FastAPI, SQLite, MCP, CLI, rendering, Git I/O. |
| composition roots | Composition only | Entry-point modules that wire the object graph. |

Composition roots (allowed to import from all packages):
- `src/infrastructure/app_bootstrap.py`
- `src/infrastructure/cli/artifact_query_cli.py`
- `src/infrastructure/cli/arch_assurance.py`
- `src/infrastructure/cli/_assurance_commands.py`
- `src/infrastructure/cli/_security_commands.py`
- `src/infrastructure/mcp/arch_mcp_stdio.py`
- `src/infrastructure/mcp/arch_mcp_stdio_write.py`
- `src/infrastructure/mcp/arch_mcp_stdio_assurance.py`
- `src/infrastructure/mcp/mcp_artifact_server.py`
- `src/infrastructure/mcp/mcp_assurance_server.py`
- `src/infrastructure/gui/gui_server.py`
- `src/infrastructure/backend/arch_backend.py`
- `src/infrastructure/backend/arch_backend_app.py`

---

&nbsp;

## Dependency matrix

```
package          may import from
──────────────   ────────────────────────────────────────────────
domain        →  domain, stdlib/third-party
application   →  domain, application, stdlib/third-party
config        →  config, domain (value types only), stdlib/third-party
ontologies/*  →  domain (contracts + types), stdlib/third-party
diagram_types/* → domain (contracts + types), infrastructure renderers, stdlib/third-party
infrastructure → application, domain, ontologies/*, diagram_types/*, config,
                  infrastructure, stdlib/third-party
composition   →  all packages
```

---

&nbsp;

## Burn-down

Known violations are recorded in `tests/architecture/architecture_baseline.json`.
The test fails only on *new* violations, so the baseline can only shrink; the goal
state is an empty baseline.

The baseline currently records three entries, all one category:

| Category | Files | Status |
|----------|-------|--------|
| `diagram_types → application` | `datatype/_contributions.py`, `datatype/_contributions_keys.py` (import verifier types from `application.verification`) | Known exception, pending a contributed-verifier contract in `domain` |
