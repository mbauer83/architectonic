# Architecture Modelling Task Sequences

Derived from the modeled workflow process **`PRC@1776635640.U4aAdh` — Architecture
Modelling & Planning**, which orchestrates discovery, authoring, verification, and
diagram scaffolding as sequential steps composed of the functions:

- `FNC@1777409722.ErTqVT` — Scope & Formulate Modelling Task
- `FNC@1777390444.lLdx12` — Discover Relevant Architecture Content
- `FNC@1777472861.HgWMdN` — Decide: Changes to Plan or Implement
- `FNC@1777409722.rkx32U` — Determine Required Changes to Architecture Content
- `FNC@1777390448.yuFXVJ` — Author Model Artifacts
- `FNC@1777390449.uzJGYp` — Author Diagrams
- `FNC@1777390454.4ce2Qt` — Synthesize & Deliver Implementation Guidance
- `FNC@1777390445.NGjUCa` — Verify Artifact Integrity & Coherence
- `FNC@1777409722.saMRQ0` — Author Architecture Documents

---

## Standard modeling lifecycle

### Step 1 — Scope & Formulate (FNC@1777409722.ErTqVT)

Read the request and conversation context. Identify:
- Which domains and entity types are likely involved.
- What architectural questions the session must answer.
- What level of confidence is needed before writing anything.

**Stop gate:** Do not start authoring until the scope is clear. For large or
structurally significant changes (new domain, plateau boundaries, significant
rewiring) present a plan and confirm before committing anything.

Scale autonomy to request size:
- **Small / clear** (1–3 entities, unambiguous types): proceed, then report.
- **Medium batch / ambiguous types**: state what you plan, then proceed unless
  the user objects.
- **Large / structurally significant**: present a plan; confirm before committing.

### Step 2 — Discover Relevant Content (FNC@1777390444.lLdx12)

Do a targeted search to find related existing content and potential duplicates:

```
artifact_query_search_artifacts(query="<key concept>", limit=10)
```

If the scope is genuinely unclear, call `artifact_query_stats` first. If a
candidate exists, read it with `artifact_query_read_artifact(mode="full")` to
decide whether to reuse, edit, or create a distinct entity.

Check for existing connections before adding any:
```
artifact_query_find_connections_for(entity_id="...", direction="any")
```

### Step 3 — Decide: Plan or Implement (FNC@1777472861.HgWMdN)

Choose the path for this session:
- If authoring model artifacts → Step 4 → Step 5.
- If authoring diagrams → Step 5 (model target must be established first; see C4
  note below).
- If authoring documents → Step 7 directly.
- If verifying only → Step 8.

**C4 / model-backed diagram rule:** Model the target state in the entity/connection
graph before creating or refreshing a C4 diagram. The projector reads from the
model — a blank model yields an empty projection, not a populated diagram.

### Step 4 — Plan Required Changes (FNC@1777409722.rkx32U)

Before authoring, resolve type and connection choices:

1. Call `artifact_authoring_guidance(filter=[...])` for each entity type you plan
   to create that has not been confirmed this session. The `create_when` /
   `never_create_when` output is authoritative.
2. **Pair-legality check before authoring any connection:** call
   `artifact_authoring_guidance(filter=["SourceType"], target="TargetType")` to
   get directional pair guidance (outgoing, incoming, symmetric). This replaces
   rejected-write retry cycles.
3. Concept check: state in one sentence what each element *is* at the conceptual
   level (not its type — its nature). If the statement sounds like a design
   decision or implementation detail rather than a named thing in the architecture,
   reconsider the type.

### Step 5 — Author Model Artifacts (FNC@1777390448.yuFXVJ) and/or Diagrams (FNC@1777390449.uzJGYp)

**Stop gate: dry-run before every write.**

- Call with `dry_run=true`. Read the `content` preview — verify type, name,
  summary, and structure are correct before committing.
- Call with `dry_run=false`. Check the `verification` field. If errors appear,
  fix the underlying issue and re-dry-run before retrying.

Batch rules:
- For interdependent creates/edits/connections, use `artifact_bulk_write` rather
  than many single calls.
- For deletions (including single), use `artifact_bulk_delete` — it is the
  canonical MCP delete surface with dependency-aware preflight.

**Safe model-backed diagram refresh:** call `artifact_edit_diagram` with
`puml="auto-sync"`. For scope-bound (projector-owned) diagrams this re-runs the
projector; it never deletes or blanks the diagram on an empty projection. See
`references/tool-examples.md` for the worked flow.

### Step 6 — Synthesize & Deliver (FNC@1777390454.4ce2Qt)

Report `artifact_id` values for every entity, connection, or diagram created or
modified this session. Describe what was done and why each element matters, in
terms the user can act on.

### Step 7 — Author Architecture Documents (FNC@1777409722.saMRQ0)

When the session requires narrative or tabular documentation alongside model
changes, use `artifact_create_document` / `artifact_edit_document`. Documents
are not a substitute for model content — both should be accurate.

### Step 8 — Verify Artifact Integrity & Coherence (FNC@1777390445.NGjUCa)

**Stop gate: artifact_verify → 0 errors before closing a session.**

After creating or modifying more than a handful of entities, or at session end:

```
artifact_verify(repo_scope="engagement", return_mode="full")
```

Fix all errors before closing. Resolve warnings on any entity you created or
modified this session. Pre-existing warnings on untouched files are not your
responsibility unless specifically asked.

---

## Common disambiguation calls

**goal vs. outcome vs. requirement:**
- Goal: desired direction ("improve reliability").
- Outcome: observable result indicating progress ("rework rate measurably reduced").
- Requirement: specific constraint the architecture must satisfy ("verify referential
  integrity on every write").
Outcomes are not required for every goal — requirements may connect directly to
goals (via influence or association) when no outcome intermediary exists.

**process vs. function:**
Ask whether the grouping principle is *sequence* (this happens, then that) or
*shared resource / capability* (same people, knowledge, or system). Sequence →
process. Shared resource → function.

**service vs. process/function:**
Service = external view (what is provided to consumers). Process/function = internal
realization (how work is done). If you're describing what something offers to the
outside world, it is a service.

**When to use pair-legality check:**
Any time you are about to add a connection and are not certain both direction and
type are permitted. One call to `artifact_authoring_guidance` with `target=` is
cheaper than an authoring error.
