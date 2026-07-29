---
name: architecture-modelling
description: >
  Use this skill whenever you are doing architectural planning, creating or updating
  architectural models, reverse architecture modelling, or verifying what was built
  against existing architectural plans. Covers ArchiMate, C4, assurance modelling,
  and SysML notation. Trigger on any request that involves modeling stakeholders,
  drivers, goals, outcomes, requirements, capabilities, courses of action, value
  streams, roles, processes, functions, services, application components, data
  objects, technology nodes, artifacts, C4 systems/containers/components, safety
  cases, STPA analyses, GRC frameworks, or system requirements against the
  architecture.
  Also trigger when the user asks to "add to the model", "connect X to Y", "what's
  in the model", "create an architecture element", "update the architecture", "check
  the architecture", "check the model", "create a C4 diagram", "model this
  component", "check the assurance case", "verify against the architecture", or
  anything that references the model or architecture repository.
---

# Architecture Modelling Skill

All model access and mutations go through `artifact_*` MCP tools from the
architecture-repository MCP servers. Read/query/verify through `arch-repo-read`;
mutations through `arch-repo-write`. Never edit model files directly — the tools
enforce verification, maintain graph integrity, and keep indexed state aligned.

**Load on demand:**
- **`references/task-sequences.md`** — step-by-step lifecycle for planning and
  executing a modelling session (derived from the modeled workflow process
  `PRC@1776635640.U4aAdh`). Load when starting or planning any session.
- **`references/tool-examples.md`** — worked flows for common tasks: safe
  model-backed diagram refresh, setting a view-specific edge label, pair-legality
  lookup, entity authoring. Load when you need a concrete example.

---

## Modelling Principles

### Domain-driven thinking first

ArchiMate is a notation language, not a thinking framework. Think first in terms of
the actual problem-space and solution-space, then determine the appropriate granularity
and entity/connection types to model the situation. Rote template application is the
main source of over-modeling, misrepresentation, and low-value content.

- **Problem space:** What forces, trends, or conditions apply? How does the problem
  decompose causally/temporally? What do stakeholders actually care about and why?
- **Solution space:** What set of concepts in what relations best captures the
  problem-space? Which roles, interaction-surfaces, and services are involved? How do
  elements trace to the motivation domain?

### Iterative, progressive modeling

Match model depth to current knowledge. Requirements may connect directly to goals
when outcomes are not yet defined — that is a valid intermediate state, not an error.
Each session should improve the highest-leverage gaps; don't wait for completeness
in one area before moving to another.

### Selective domain coverage

Domain applicability heuristics:
- **Motivation** — almost always relevant; get this right first.
- **Common / Business / Application** — the typical working layers.
- **Implementation & Migration** — only when the engagement explicitly plans or
  tracks change; infer from context.
- **Strategy** — only for structural changes to the business itself.
- **Technology** — only when architectural questions directly concern infrastructure
  or deployment.

### Pareto principle — minimal sufficient coverage first

Identify the highest-leverage elements first — the ones without which the key
architectural questions cannot be answered. Resist comprehensiveness; fewer
well-chosen elements are more useful than more vague ones.

---

## Model vs. Diagram vs. Documents — Three Distinct Activities

**Model:** the persistent knowledge graph. Breadth is acceptable when the Pareto
principle is applied — include what is architecturally significant.

**Diagram:** a focused viewpoint for a specific audience answering one question.
Before creating one, establish: audience, the one question it answers, and what
is deliberately excluded. Start from a small set of central elements and add by
following the most architecturally significant relationships. Many small diagrams
are more useful than one large one. Prefer matrix diagrams for dense many-to-many
relationships.

**Documents:** narrative or tabular documentation alongside the model, not instead
of it. Use `artifact_create_document` / `artifact_edit_document`.

**PlantUML rules (hard-won — violating these causes rendering errors):**
- **Verify connections in the model before drawing them.** Use
  `artifact_query_find_connections_for` on each source entity; never assume a
  connection exists.
- **No newlines in label strings.** `\n` is passed as a literal 0x0A inside
  double-quoted PUML strings — use single-line labels only.
- **Direction:** `left to right direction` for wide, shallow diagrams;
  `top to bottom direction` for tall, multi-layer chains.
- **Realization arrows** point from concrete to abstract. LTR:
  `TARGET -left-|> SOURCE : <<realization>>`. TTB: `TARGET -up-|> SOURCE`.
- **Upward edges in TTB layouts need explicit hints** — `.up.>` (dotted influence),
  `.up.|>` (dotted realization). A plain `..>` pointing at a node ranked above gets
  its rank reversed by graphviz and collapses the layout.
- **Cross-band edges that must not affect ranking** (e.g. a lower group's goal
  influencing an upper group's goal): use `-[dotted,norank]->`.
- **Edge labels:** pad with `<U+00A0>` on both ends (`: <U+00A0>(+)<U+00A0>`) for
  horizontal clearance beside vertical edges. Labels on HORIZONTAL edges are centered
  ON the line under dot/ortho — they will overlap the dashes; omit them or restructure.
- **Sprite scale:** use `{scale=1.2}` in entity labels — at 1.5 the 24px sprite pushes
  the text baseline ~4px below the box center (labels look too low). CAUTION: node-size
  changes can trip a PlantUML ortho/cluster layout bug (UnparsableGraphvizException —
  PlantUML exits 0 but writes an ERROR IMAGE, trace on stderr). If a diagram hits it,
  nudge the scale (e.g. 1.25) or nodesep/ranksep and re-render; always eyeball the
  rendered PNG after layout-affecting edits.
- **Header refresh:** stored .puml files bake the injected header (fonts, sprites,
  skinparams). After changing `archimateGlyphs.json` or the header template, regenerate
  includes (`python -m src.infrastructure.rendering.generate_static_includes <repo>`)
  and re-write each diagram body via `artifact_edit_diagram` (viewpoint-backed diagrams:
  `puml='auto-sync'`; hand-authored: pass the body explicitly — auto-sync would
  regenerate it from bindings and destroy the layout).
- **`together {}` is broken.** `linetype ortho` (set globally) is incompatible;
  use named containers instead.
- **No phantom helper nodes.** `-[hidden]->` on transparent rectangles fails with
  E350. Use `-[hidden]right-` / `-[hidden]down-` between real model elements only.
- **Read an existing working diagram first** before attempting a layout pattern
  you haven't used in this repo.

**Multi-layer TTB layout (alternating H/V groupings):**

```plantuml
top to bottom direction
rectangle "Layer A" <<MotivationGrouping>> {
  rectangle "..." <<Driver>> as A1
  rectangle "..." <<Driver>> as A2
}
A1 -[hidden]right- A2
rectangle "Layer B" <<MotivationGrouping>> {
  rectangle "..." <<Assessment>> as B1
  rectangle "..." <<Assessment>> as B2
}
B1 -[hidden]down- B2
A2 -[hidden]down- B1            ' inter-layer anchor
B1 -up-|> A1 : <<realization>>  ' concrete → abstract
```

---

## MCP Tool Map

### Server split

- `arch-repo-read` — query and verify only (read-only).
- `arch-repo-write` — create, edit, delete, promote, save/review. Also hosts the
  read-only guidance tools (`artifact_help`, `artifact_authoring_guidance`).
- Use `artifact_bulk_delete` for all deletes — the single-item delete is not
  exposed on the MCP surface.

### Orientation
| Tool | When to use |
|---|---|
| `artifact_query_stats` | Broad orientation at session start; skip when request is specific. |
| `artifact_help` | When uncertain about a type name or diagram type identifier — returns the full catalog. |

### Reading and searching
| Tool | When to use |
|---|---|
| `artifact_query_list_artifacts` | List with AND-filtered metadata (domain, type, status). |
| `artifact_query_read_artifact` | Read one artifact; `mode="summary"` or `mode="full"`. |
| `artifact_query_search_artifacts` | Keyword search; use for duplicate checks. |
| `artifact_query_find_connections_for` | Connections on a specific entity; filter by direction/type. |
| `artifact_query_find_neighbors` | Graph traversal; control `max_hops` and connection-type filter. |
| `artifact_diagram_scaffold` | Suggest scope + PUML scaffold from a selected entity set. |

### Guidance
| Tool | When to use |
|---|---|
| `artifact_authoring_guidance` | **Call before creating** entities, connections, or diagrams. `filter=[types]` or `filter=[domain]` for entity guidance; `diagram_type="..."` for diagram guidance; `target="TypeB"` with a single-type `filter` to get directional pair-legality for source→target. Output is authoritative — supersedes any quick-reference table. |

### Creating
| Tool | When to use |
|---|---|
| `artifact_create_entity` | Create entity; always `dry_run=true` first. |
| `artifact_add_connection` | Add connection; `dry_run=true` first; auto-creates GRF proxy for enterprise targets. |
| `artifact_bulk_write` | Coordinated batches of creates/edits/connections. |
| `artifact_create_diagram` | Create diagram after model content and viewpoint are clear. |
| `artifact_create_matrix` | Matrix diagram for dense many-to-many relationships. |
| `artifact_create_document` | Narrative or tabular architecture document. |

### Editing
| Tool | When to use |
|---|---|
| `artifact_edit_entity` | Update name/summary/properties/notes/keywords/version/status; `dry_run=true` first. |
| `artifact_edit_connection` | Update or remove a connection; `dry_run=true` first. |
| `artifact_edit_connection_associations` | Add/remove `§assoc` secondary relationships on a connection. |
| `artifact_edit_diagram` | Refine entity/connection scope or set per-diagram `edge_labels` overrides. |
| `artifact_edit_document` | Update an existing document. |
| `artifact_bulk_delete` | All deletes — single or batch; dependency-aware preflight. |
| `artifact_promote_to_enterprise` | Promote engagement entities to enterprise; `dry_run=true` first. |

### Verification
| Tool | When to use |
|---|---|
| `artifact_verify` | Batch-end or session-end repo-wide check. `return_mode="full"` for per-issue detail. Fix all errors; resolve warnings on entities you created or modified. |

### Save / review
| Tool | When to use |
|---|---|
| `artifact_save_changes` | Commit a coherent batch of modeling changes. |
| `artifact_submit_for_review` | Push enterprise working-branch changes for team review. |
| `artifact_withdraw_changes` | Discard enterprise working-branch changes (destructive). |

---

## Authoring Notes

**Entity summaries:** One sentence answering *what is this element and what role does
it play?* Avoid restating the name. A requirement summary states the actual constraint;
a process summary states what it does and why it matters.

**Multiplicity:** Add `src_multiplicity` / `tgt_multiplicity` on
`artifact_add_connection` only when multiplicity is architecturally significant.
Valid values: `"1"`, `"0..1"`, `"1..*"`, `"*"`. Not permitted on junction connections.

**Repo scoping:** Query tools default to `repo_scope="both"`; narrow to
`"engagement"` or `"enterprise"` as needed. Write tools target the current engagement
repo. `artifact_add_connection` handles GRF proxy creation automatically for
cross-repo connections.
