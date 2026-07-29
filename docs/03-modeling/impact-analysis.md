# Impact analysis

"What is affected if this element changes?" and "what indirectly supports this element?" are
questions a flat model of direct connections can't answer on its own — the chain of real
relationships that actually links two elements is often several hops long, through elements
neither question cares about. Impact analysis answers them by **deriving** indirect
relationships from the connections that already exist, on demand, without adding anything to
the model.

This page is the explanation and how-to; the query-level mechanics (`traversal`,
`include_potential`, `max_hops`) are covered as part of the general query grammar in
[Viewpoints](viewpoints.md#traversal-direct-vs-derived-certain-vs-potential).

&nbsp;

## Relationship derivation vs. view derivation

Two unrelated things share the word "derived" in this system — worth naming precisely once:

- **Relationship derivation** (this page) — computing an *indirect relationship* between two
  elements from a chain of real, modeled relationships. Purely a query-time computation; a
  derived relationship is never written anywhere. Re-run the same query tomorrow and it's
  recomputed from whatever the model contains then.
- **View derivation** — an unrelated, older mechanism for generating a *diagram's population*
  (which entities/connections to place) from a strategy, distinct from hand-placing entities
  one at a time. A generated diagram can itself use `traversal: derived` connections as part
  of its population, but the two concepts compose rather than overlap.

&nbsp;

## Certain vs. potential

Not every indirect relationship a derivation chain suggests is equally trustworthy. ArchiMate
4.0's Appendix B splits derivation into two kinds:

- **Certain (DR rules)** — true in *any* model where the rule's precondition holds. Certain
  derivations compose two relationships of the same *role* (see below) — for example, two
  structural relationships joined at a shared element always yield a valid structural
  relationship, no matter what those two relationships happen to mean in this specific model.
- **Potential (PDR rules)** — plausible, but not guaranteed — composing relationships of
  *different* roles (a structural relationship joined with a dependency relationship, say)
  produces a relationship type that's often right but depends on modeling intent the two
  source relationships alone don't fully determine. A potential derivation is a candidate for
  a human (or an agent under human direction) to accept or reject, never a fact asserted
  outright.

A query's `include_potential` flag controls whether potential derivations count at all
(default: no) — many questions ("what does this component depend on for certain") only make
sense scoped to certain relationships; others ("what could plausibly be affected") want the
wider, less certain net.

&nbsp;

## Composing relationships: role and strength

Two relationships compose into a derived one only when they join at a shared element (one's
target is the other's source) and their **roles** are compatible. Each ArchiMate relationship
type carries a derivation role and, within structural and dependency roles, a strength —
the derived relationship takes the *weakest* of the two it's composed from:

| Role | Types, strongest to weakest |
|---|---|
| Structural | Composition (4) → Aggregation (3) → Assignment (2) → Realization (1) |
| Dependency | Serving (4) → Access (3) → Influence (2) → Association (1) |
| Specialization | Specialization only (transitive with itself) |
| Dynamic | Flow, Triggering (not currently composed by this engine) |

A structural relationship can also compose with a dependency relationship that joins at the
same point (e.g. "A is composed of B" + "B serves C" → "A serves C, potentially") — the
resulting relationship takes the dependency relationship's type, since that's the one
carrying directional meaning forward.

**Association is deliberately excluded from further composition.** It's the weakest
dependency type and carries no directional semantics to propagate — composing *through* an
association would manufacture meaning the model never actually asserted. Association can
still be the outermost relationship of a derived chain (composed *onto* by a stronger
relationship reaching it), just never a link a further derivation composes *across*. This is
a real, occasionally surprising boundary in practice: two elements that look "obviously"
connected through a chain of relationships may have no derivable path at all if the only
route between them passes through an association — that's the derivation rules working
correctly, not a gap to route around.

&nbsp;

## Impact workflows

- **GUI — ad-hoc exploration**: `/graph/layered` builds an unpersisted layered or
  motivation-support view — pick root elements (by name/id or by criteria), choose which
  indirectly-connected element kind to pull in, and render. Selecting a derived arrow opens a
  witness-chain explanation: the real relationships that compose it, in order, with clickable
  entity links. Nothing here is saved unless a candidate is explicitly materialized (below).
- **GUI — the diagram viewer**: any executed `diagram`-representation viewpoint (ad-hoc or a
  saved definition) shows derived connections in their derived type's ordinary ArchiMate
  notation, marked with a certainty indicator. Clicking one opens the same witness-chain
  explanation in the entity sidebar.
- **GUI — the Query model page**: `/viewpoints/query` composes a full impact-analysis query
  *and* a presentation (e.g. an anchored, derived-traversal query shown as exploration, table,
  matrix, or diagram) and runs it as an unsaved viewpoint — nothing is persisted, and the whole
  flow works in read-only mode. "Save as viewpoint…" hands the composed query + presentation to
  the definition editor if you decide to keep it.
- **MCP — direct queries**: `artifact_query_find_neighbors` (`traversal: derived`,
  `include_potential`, `max_hops`) for ad-hoc graph exploration from a single entity;
  `artifact_query_viewpoint` `execute` for a full saved or inline query, including
  `certainty`/`hops`/`via_connection_ids` on every derived connection in the response.
- **Parameterized default viewpoints**: `element-dependents` ("what is affected if ⟨anchor⟩
  changes," incoming derived traversal) and `element-dependencies` (the outgoing mirror,
  "what does ⟨anchor⟩ depend on") ship in the module library, ready to execute against any
  entity without authoring anything.
- **Generated impact diagrams**: the same derivation engine backs a *persisted* diagram
  generation strategy (`derived_relationships`), so an impact analysis can also be captured
  as a real, versioned diagram artifact rather than a one-off query — subject to the usual
  accept/reject review for potential candidates, and to refresh staleness if the underlying
  model changes under an accepted path later.

&nbsp;

## Materializing a potential relationship

Reviewing a potential derivation and deciding it should really be a modeled fact doesn't
require a separate write path: the GUI's "materialize" action on a derived candidate
pre-fills the ordinary connection-creation flow (type, endpoints, and a description noting
the witnessing chain it came from) — the same `artifact_add_connection` tool an agent would
use directly. There's no automatism that writes a derived relationship into the model on its
own; a human (or an agent acting under explicit direction) always makes that call.

---

*Next: [Interfaces & MCP →](interfaces-and-mcp.md)*
