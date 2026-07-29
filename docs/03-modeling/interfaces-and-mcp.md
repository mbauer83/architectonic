# Interfaces & MCP

Three surfaces sit over one artifact store: an **MCP server** for AI agents, a **REST API**
for programmatic access, and a **browser GUI** for people. The GUI is built on the REST API,
so anything a human can do in the browser can be automated through REST or MCP.

The principle behind this is deliberate: *architecture work is reachable through both human
and agent interfaces*, without claiming identical depth on every feature. Agent access is
designed in from the start — typed tools with built-in schema validation and verification, an
authoring surface an agent can write to safely — rather than an export or read-only API
bolted onto a human-first tool.

&nbsp;

## MCP tool surface

The MCP interface is split into two servers so an agent can be constrained by capability.
Configure them in `.mcp.json` — see [Installation §5](../02-installation.md#5-configure-mcp-access-for-ai-agents).

### `arch-repo-read` (query, navigate, verify)

<!-- mcp-tools:begin arch-read -->
| Tool | Access | Purpose |
|---|---|---|
| `artifact_aibom_coverage` | Read-only | Per-AI-component AIBOM coverage over the architecture model: blocking gaps (missing required attributes, missing dataset linkage, missing governance edge) vs advisory gaps (missing recommended attributes), plus repo-wide derivation roles that no connection type is bound to. |
| `artifact_aibom_export` | Read-only | Emit a CycloneDX 1.6 ML-BOM DERIVED from the architecture model: every entity carrying an AI specialization (ai-model, ai-agent, ai-inference-service, ai-dataset, ai-prompt-asset, ai-vector-store, ai-runtime, ai-tool-interface) becomes a component, with its authored model card, dataset/governance links resolved from connections, and a dependency graph between AI components. |
| `artifact_diagram_scaffold` | Read-only | Generate a ready-to-edit @startuml…@enduml scaffold from a list of entity IDs. |
| `artifact_query_datatype_types` | Read-only | List available attribute types for datatype diagrams. |
| `artifact_query_find_connections_for` | Read-only | Find connection records that touch a given entity_id. |
| `artifact_query_find_neighbors` | Read-only | Graph traversal: return direct or derived neighbors within max_hops. |
| `artifact_query_list_artifacts` | Read-only | List artifacts (metadata-only) with AND-semantics filters. |
| `artifact_query_read_artifact` | Read-only | Read one artifact by artifact_id. |
| `artifact_query_search_artifacts` | Read-only | Search artifacts by text query (keyword-scored; may include semantic supplement if configured). |
| `artifact_query_stats` | Read-only | Return model statistics: total entity/connection/diagram counts and breakdowns by domain, connection type, and group. |
| `artifact_query_viewpoint` | Read-only | action='list': browse the effective merged viewpoint catalog — slug/version/name/purpose/content/stakeholders/concerns, a scope summary, a plain-language query_summary so you see what a viewpoint means, not just that it exists, and whether it is pinned (engagement-repo-local quick access). |
| `artifact_verify` | Read-only | Verify one file or all model files. |
<!-- mcp-tools:end arch-read -->

### `arch-repo-write` (author, edit, promote)

<!-- mcp-tools:begin arch-write -->
| Capability | Tool | Access | Purpose |
|---|---|---|---|
| Entities | `artifact_create_entity` | Write | Create a model entity file. |
| Entities | `artifact_edit_entity` | Write | Edit an existing entity. |
| Entities | `artifact_delete_entity` | Destructive | Delete a single entity (and its own .outgoing.md file, if any). |
| Connections | `artifact_add_connection` | Write | Add a connection to an entity's .outgoing.md file. |
| Connections | `artifact_edit_connection` | Write | Edit or remove a connection in an .outgoing.md file. |
| Connections | `artifact_edit_connection_associations` | Write | Add or remove second-order association entity IDs from a connection. |
| Diagrams | `artifact_create_diagram` | Write | Create a diagram. |
| Diagrams | `artifact_edit_diagram` | Write | Edit an existing diagram. |
| Diagrams | `artifact_delete_diagram` | Destructive | Delete a single diagram, including its rendered PNG/SVG output. |
| Diagrams | `artifact_create_matrix` | Write | Create a markdown connection-matrix diagram. |
| Documents | `artifact_create_document` | Write | Create a new architecture document (e.g. ADR, RFC). |
| Documents | `artifact_edit_document` | Write | Edit an existing architecture document's frontmatter or body. |
| Documents | `artifact_delete_document` | Destructive | Delete a single architecture document. |
| Bulk | `artifact_bulk_write` | Write | Batch entity creates, connection adds, and edits in one call. |
| Bulk | `artifact_bulk_delete` | Destructive | Batch destructive operations with dependency-aware planning and final repository verification. |
| Grouping | `artifact_group` | Write | Manage artifact group containers across all three grouping axes. |
| Promotion & sync | `artifact_promote_to_enterprise` | Write | Promote an explicit selection of entities, connections, documents, and diagrams from the engagement repo to the enterprise repo (entity_ids, connection_ids, document_ids, diagram_ids; entity_id names the selection root). |
| Promotion & sync | `artifact_save_changes` | Write | Commit all accumulated architecture changes. |
| Promotion & sync | `artifact_submit_for_review` | Write | Push the enterprise working branch to the remote for team review. |
| Promotion & sync | `artifact_withdraw_changes` | Destructive | Permanently discard all pending enterprise changes (requires confirm=True). |
| Guidance & ops | `artifact_authoring_guidance` | Write | Return authoring guidance before creating entities or diagrams. |
| Guidance & ops | `artifact_help` | Write | Return the full catalog of artifact types, entity types (by domain), connection types (by language), and diagram types (with accepted domains). |
| Guidance & ops | `artifact_get_operation` | Write | Return the latest recorded status, phase, timestamps, error, and final result for a prior bulk operation by operation_id. |
| Guidance & ops | `artifact_admin_reindex` | Destructive | Rebuild the artifact index from disk. |
| Other | `artifact_viewpoint` | Write | Create/edit/delete a ViewpointDefinition in the engagement repo's own catalog — the same validate/persist path a GUI builder's save flow uses. |
<!-- mcp-tools:end arch-write -->

The tool count is kept small with clear descriptions on purpose — fewer, well-described
tools let an agent pick correctly. Every write tool validates against the verifier, supports
a dry-run preview, and returns structured error codes with locations on failure. Structured
output is returned as YAML for token efficiency. The tables above are generated from the
registered MCP servers by `uv run tools/docs/generate_mcp_docs.py`.

Every mutation — MCP tool or REST route — executes through one authorized path: a closed
per-intent policy checked against a fresh authority snapshot, then the shared single-writer
queue and workspace write gate. Standard authoring tools are **engagement-only in every
mode** and accept only the configured active engagement root (an explicit `repo_root`
pointing at the enterprise repository — or a child, relative, or symlinked spelling of it —
is rejected with an error naming the admin surface). Promotion, enterprise save, submit, and
discard are the only enterprise writes outside admin mode; `--read-only` denies every
architecture-repository mutation on every interface. Save commits run the artifact verifier
over the whole working tree (it may contain manual edits); only content-neutral git
operations — Submit's push of already-committed work and Discard's branch cleanup — are
exempt.

> The optional **assurance** MCP servers (`arch-assurance-read` / `arch-assurance-write`)
> are documented separately under [Assurance MCP tools](../04-assurance/mcp-tools.md).

&nbsp;

## Inspecting the live tool surface

To browse the running MCP surface with the MCP Inspector over stdio:

```bash
tmp_cfg="$(mktemp)"
cat >"$tmp_cfg" <<JSON
{
  "mcpServers": {
    "default-server": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "$(pwd)", "run", "arch-mcp-stdio-read"]
    }
  }
}
JSON
npx -y @modelcontextprotocol/inspector@latest --config "$tmp_cfg" --server default-server
```

Swap `arch-mcp-stdio-read` for `arch-mcp-stdio-write` to inspect the write server. The
explicit `stdio` config avoids stale persisted transport state in the Inspector UI.

&nbsp;

## REST API

`arch-backend` exposes the same capability set at `http://localhost:<backend-port>/api/`.
Because the GUI is built on it, the REST surface covers querying, authoring, verification,
promotion, grouping, and the save/submit/review sync lifecycle. A Server-Sent Events stream
at `GET /api/events` carries sync progress and write-lock state.

&nbsp;

## Browser GUI

`arch-backend` serves the Vue SPA at `/`. It covers:

- **Overview** — engagement vs. enterprise summary, domain and connection-type breakdowns
- **Exploration** — entity / diagram / document catalogs with filtering, search, treemap,
  and graph navigation
- **Authoring** — schema-aware entity / diagram / document creation and editing with live
  preview
- **Verification** — real-time validation feedback and promotion conflict detection
- **Promotion** — explicit entity/connection curation with conflict-resolution strategies

---

*Back to [Architecture Modeling](index.md) · Next section: [Assurance →](../04-assurance/index.md)*
