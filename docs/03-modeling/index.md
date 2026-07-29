# Architecture Modeling

> Modeling aims for conformance with the
> [ArchiMate 4.0](../reference/archimate-4-conformance.md) standard; conformance has not
> been independently verified, so no conformance claim is made.

The model is a graph of typed **entities** connected by typed **connections**, organised
into **domains** (motivation, strategy, business, application, technology, implementation,
and a common cross-domain layer) and rendered through several **diagram families**. Every
artifact is a git-versioned markdown file with structured frontmatter, reachable through the
GUI, the REST API, the CLI, and the MCP tools.

&nbsp;

## On this page set

| Page | What it covers |
|---|---|
| [Projects & grouping](projects-and-grouping.md) | The three independent grouping axes and the group lifecycle |
| [Views & exploration](views-and-exploration.md) | List view, treemap, grid, full-text search, and graph navigation |
| [Diagramming](diagramming.md) | ArchiMate, matrix, activity, sequence, C4, and datatype (UML class) diagram families |
| [Viewpoints](viewpoints.md) | Saved, criteria-based ways of looking at a slice of the model — definitions, applications to existing diagrams, and ad-hoc execution |
| [Motivation coverage](coverage-semantics.md) | What "covered" means when a goal fans out — branch-complete realization, obligations for absent nodes, and why a diagnostic observation is never a gap |
| [Impact analysis](impact-analysis.md) | Deriving indirect relationships from real connections — certain vs. potential, impact workflows, materializing a derived relationship |
| [Interfaces & MCP](interfaces-and-mcp.md) | The MCP read/write tool surface, REST API, and GUI parity |

&nbsp;

## The artifact families

Four kinds of artifact share one consistent metadata model (name, version,
`status` ∈ {draft, active, retired}, keywords, timestamps):

- **Entities** — typed nodes scoped to a domain (Goal, Requirement, Capability, Service,
  Application Component, Node, …). Each entity is a standalone file.
- **Connections** — typed, directed relationships (realizes, supports, composes,
  specializes, serves, …) with optional source/target multiplicity and a description.
- **Diagrams** — views over the model, in one of the diagram families below.
- **Documents** — ADRs, standards, specifications, and other structured docs with required
  sections and frontmatter (see [Document types](../05-extensibility/document-types.md)).

&nbsp;

## The two-tiered repository

Modeling happens against two repositories:

- **Engagement repo** — project-specific work. New entities, connections, diagrams, and
  documents are created here.
- **Enterprise repo** — the curated, organization-wide baseline. Engagement tools read it
  but do not write to it directly.

Content moves up through an explicit, traced **promotion** step. Enterprise entities may
only reference other enterprise entities; engagement entities may reference both. The
verifier enforces this asymmetry. See
[Git sync & promotion](../reference/git-sync-promotion.md) for the full lifecycle.

&nbsp;

## Always-on verification

Every write is verified before it commits, and the whole repository can be verified on
demand. Checks cover schema conformance, referential integrity, cross-repo reference rules,
PlantUML diagram syntax, and document frontmatter and section structure. Agents receive
structured error codes and locations; humans see inline feedback in the GUI.

---

*Next: [Projects & grouping →](projects-and-grouping.md)*
