# Exploring Assurance Content

The assurance store is a typed graph — losses, hazards, control structures, constraints,
risks, obligations — and it is explorable the same three ways the architecture model is:
browse, detail, and interactive graph traversal. Everything on this page is read-side;
for creating analyses and running the guided methods, see [Methods](methods.md).

All of it sits behind the store's gating: a locked store renders a locked banner and
fetches nothing, and every result is **exposure-filtered** — content above your TLP
ceiling is absent, not redacted in place. See
[Storage & confidentiality](storage-and-confidentiality.md).

&nbsp;

## Browsing

`/assurance/browse` lists the store's nodes with type and analysis filters next to a
detail pane — the assurance counterpart of the entities list. The assurance overview
(`/assurance`) summarizes the store: analyses, node counts, store and unlock state.

For agents, the same reads are `assurance_list_analyses`, `assurance_list_nodes`, and
`assurance_read_node` on the `arch-assurance-read` MCP server.

&nbsp;

## Node detail — a deep-linkable page per node

Every assurance node has a standalone page at `/assurance/node/<id>`, so a hazard or a
constraint can be linked directly from a review comment, a ticket, or another tool. The
page shows the node's fields, its incoming and outgoing edges, and its analysis context.

Two deliberate properties:

- **Unknown and above-ceiling ids are indistinguishable** — both render the identical
  not-found page. A link to a node you cannot see does not confirm the node exists.
- A locked store renders the locked banner rather than an error, matching every other
  assurance surface.

&nbsp;

## Graph traversal

`/assurance/graph` is the neighborhood explorer: it renders the traversal from
`GET /api/assurance/neighbors` on the shared graph canvas (the same canvas the
architecture graph explorer uses). Start from any node — the detail pages link into it —
and expand a node with a double-click, which issues a fresh one-hop request.

Traversal is budgeted, not unbounded: node, edge, and wall-clock budgets produce
deterministic partial results with an explicit frontier (expanding a frontier node is
also how you continue past a size budget — there are no continuation tokens). The
budgets and their hard clamps are configurable — see
[Configuration](../reference/configuration.md#configsettingsyaml--backend).

&nbsp;

## Edges: typed, and authored against the ontology

Edges between assurance nodes are typed by the assurance ontology — `caused-by`,
`explained-by`, `derives`, `assesses`, and so on — and the legal edge types depend on
the concrete node-type pair. That vocabulary is served, not hardcoded:
`GET /api/assurance/edge-catalog` returns the legal set, and the GUI's edge picker on a
node's detail page offers **exclusively** those types for the selected pair, in either
direction, with targets found through the exposure-filtered search. An edge the catalog
does not permit cannot be authored — the same rule the write surfaces
(`assurance_add_edge`, REST) enforce server-side.

&nbsp;

## Failure modes in the explorer and on node detail

A failure mode is an ordinary node in all of the above: it lists and filters at
`/assurance/browse` like any other type, has its own page at `/assurance/node/<id>`, and expands
in the graph explorer. What is worth knowing is which of its edges carry the analysis.

- **Outward to a hazard** (`leads-to`) — the failure's effect. Expanding it continues into the
  hazard's own neighbourhood and on to the losses that give the failure its severity, so the whole
  chain from a component's failure to a stakeholder loss is one traversal.
- **Inward from a constraint** (`detects`) — the controls that would reveal this failure before its
  effect propagates. These are what its detectability is read from, so an empty inward set is not a
  neutral fact about the diagram; it is the reason a priority cannot be derived.
- **Inward from a loss scenario** (`explains`) — where a causal pathway already accounts for this
  failure.

Node detail shows the guideword the failure mode was enumerated against, whether it is hypothesized
or observed, its three factors with the basis of each (derived, or asserted with its rationale and
author), and its Action Priority. A factor asserted against a picture of the model that has since
changed is marked stale, and the derived value is what applies until it is re-judged.

&nbsp;

## Crossing into the architecture model

Assurance nodes reference architecture entities one-way (a control-structure node binds
to a component; a constraint refines a requirement). Node detail surfaces those
references as links into the architecture views, so a traversal that ends at a bound
node continues naturally into the entity detail page and the architecture graph
explorer. The reverse direction is deliberately absent: architecture artifacts never
carry persisted references into the confidential store.

The **assurance lens** on an entity's detail page is how the crossing reads from the other side
without breaking that rule. It is a read-time join, not a stored back-reference: given an entity, it
asks the store which nodes bind to it and shows them, including a roll-up of that element's
failure-mode row — its worst Action Priority, how many cells are `high`, and how many guidewords
nobody has examined yet. A locked store shows the locked banner; an above-ceiling finding is simply
not in the roll-up.

---

*Next: [Diagrams →](diagrams.md)*
