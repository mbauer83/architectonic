# Architecture Modelling — Worked Tool Flows

Concrete examples for the most common and non-obvious tasks. Each flow
shows the exact tool calls, in order, with the key parameters.

---

## Flow 1 — Safe model-backed diagram refresh

**When:** You want to refresh a scope-bound (projector-owned) C4 diagram to
reflect current model state. The diagram has a `scoped-by` binding in its
frontmatter.

**Before this fix was available** the `auto-sync` path would delete a diagram
whose projection came back empty. The service is now projection-aware: for
scope-bound diagrams it re-runs the projector and never deletes.

**Steps:**

```
# 1. Read the diagram to confirm it is scope-bound (has scoped-by binding)
artifact_query_read_artifact(
  artifact_id="DGM@...",
  mode="full"
)
# Look for "scoped-by: ..." in the frontmatter.

# 2. Dry-run the refresh — must be byte-for-byte non-mutating if nothing changed
artifact_edit_diagram(
  artifact_id="DGM@...",
  puml="auto-sync",
  dry_run=True
)
# Verify: no errors in response; check content matches current file state.

# 3. Commit the refresh
artifact_edit_diagram(
  artifact_id="DGM@...",
  puml="auto-sync",
  dry_run=False
)
```

**Invariants enforced by the service:**
- A scope-bound diagram is never deleted, even if the projection is empty.
- The `scoped-by` binding, include/exclude selection, diagram type, name,
  status, version, keywords, and derivations are all preserved.
- Dry-run is byte-for-byte non-mutating.

---

## Flow 2 — Set a view-specific edge label

**When:** You want to display a custom label on a rendered connection in one
diagram (e.g., "Reads/writes audit log") without changing the model connection's
semantics or affecting the same connection's label in other diagrams.

Edge labels are keyed by `"{src_alias}:{tgt_alias}"` — the rendered PUML alias
pair for the source and target entities in that diagram.

**Steps:**

```
# 1. Read the diagram to find the rendered alias pair
artifact_query_read_artifact(
  artifact_id="DGM@...",
  mode="full"
)
# In the PUML body, find the connection line:
#   APP_hkrdtm --> APP_Z_fI-N : ...
# The edge key is "APP_hkrdtm:APP_Z_fI-N"

# 2. Dry-run the label override
artifact_edit_diagram(
  artifact_id="DGM@...",
  edge_labels={"APP_hkrdtm:APP_Z_fI-N": "Reads/writes audit log"},
  dry_run=True
)

# 3. Commit
artifact_edit_diagram(
  artifact_id="DGM@...",
  edge_labels={"APP_hkrdtm:APP_Z_fI-N": "Reads/writes audit log"},
  dry_run=False
)

# 4. To clear the override and revert to the derived label, set the value to null
artifact_edit_diagram(
  artifact_id="DGM@...",
  edge_labels={"APP_hkrdtm:APP_Z_fI-N": None},
  dry_run=False
)
```

**Notes:**
- Overriding in one diagram does not affect the same connection's label in
  any other diagram — labels are per-diagram.
- The verifier flags dangling overrides (edge alias pair no longer rendered).
- The REST equivalent is `PUT /api/diagram/edge-label` with body
  `{artifact_id, edge_key, label}`.

---

## Flow 3 — Pair-legality lookup before authoring a connection

**When:** You are about to add a connection between two entity types and want to
confirm which connection types are permitted and in which direction, before writing
anything.

This avoids rejected-write retry cycles — one call returns the full directional
picture for the source→target pair.

**Steps:**

```
# Single call: pass the source type in filter and the target type in target
artifact_authoring_guidance(
  filter=["application-component"],
  target="data-object"
)
```

**What the response includes** (in the `pair_guidance` block):
- `source` and `target` type names
- `outgoing`: connection types permitted from source → target
- `incoming`: connection types permitted from target → source
- `symmetric`: connection types valid in either direction

**Validation rules:**
- `target` is only valid when `filter` contains exactly **one concrete entity
  type** (not a domain name). Mixing domain filters with `target` → validation
  error.
- Unknown types → the tool returns known-type suggestions.

**Example decision:** if `outgoing` includes `archimate-access`, add the
connection with `conn_type="archimate-access"` from the component to the
data-object. If it does not appear, use `archimate-association` (symmetric,
always valid between any two types) or reconsider the model design.

---

## Flow 4 — Author a new entity batch (with duplicate check)

**When:** You need to create several related entities in a coordinated pass.

**Steps:**

```
# 1. Search for existing content to avoid duplicates
artifact_query_search_artifacts(query="event sourcing audit", limit=10)

# 2. Get authoritative guidance for the types you plan to use
artifact_authoring_guidance(filter=["requirement", "outcome"])

# 3. Pair-legality for the connection you plan to add
artifact_authoring_guidance(
  filter=["outcome"],
  target="goal"
)
# Confirms: outcome --realization--> goal is permitted

# 4. Bulk dry-run: plan the full batch before committing any of it
artifact_bulk_write(
  items=[
    {
      "op": "create_entity",
      "artifact_type": "outcome",
      "name": "Audit trail completeness verified on every write",
      "summary": "..."
    },
    {
      "op": "create_entity",
      "artifact_type": "requirement",
      "name": "Every model mutation must emit a verifiable audit entry",
      "summary": "..."
    }
  ],
  dry_run=True
)
# Review the previews.

# 5. Commit (dry_run=False on the bulk call)

# 6. Add connection
artifact_add_connection(
  source_entity="OUT@...",
  target_entity="GOL@...",
  connection_type="archimate-realization",
  dry_run=True
)
artifact_add_connection(
  source_entity="OUT@...",
  target_entity="GOL@...",
  connection_type="archimate-realization",
  dry_run=False
)

# 7. Session-end verify
artifact_verify(repo_scope="engagement", return_mode="full")
```
