# Viewpoints

A **viewpoint** (ArchiMate 4.0 Chapter 13) is a saved, reusable way of looking at a slice of
the model — which entities and connections it covers, and how they're presented. Instead of
hand-curating a diagram's entity list every time a question comes up ("which application
components serve a business process, and which processes do they serve?"), a viewpoint
definition answers it on demand, against whatever the model currently contains.

This page is the explanation and how-to; the full YAML shape, comparator semantics, and MCP
tool parameters are in [Viewpoints — schema reference](../reference/viewpoints-schema.md).

For coverage viewpoints specifically — what counts as "covered" when a goal fans out into
several branches, and why an absent diagnostic observation is not a gap — see
[Motivation coverage](coverage-semantics.md).

&nbsp;

## Definitions, applications, and ad-hoc execution

Three related but distinct things share the word "viewpoint":

- **`ViewpointDefinition`** — the reusable, versioned thing: a slug, a name, a purpose/content/
  stakeholders/concerns description, a **query** (which entities/connections match), and a
  **presentation** (how to show them). Definitions live in a two-tier catalog — an
  informative library shipped by the `archimate_4` module (the ArchiMate Appendix-C example
  viewpoints plus a few tool-specific impact-analysis ones), plus repo-authored definitions in
  `.arch-repo/viewpoints.yaml` at the enterprise and engagement tiers, merged the same way
  [specializations](../05-extensibility/ontology-modules.md#specializations) are.
- **`ViewpointApplication`** — pinning an *existing* diagram or matrix to a definition (at a
  specific version), non-destructively. The diagram's own placed entities/connections don't
  change; the application adds an overlay that flags which of them fall outside the
  definition's scope or fail its query, so the artifact and the viewpoint's intent can be
  compared over time as both evolve.
- **Ad-hoc execution** — running a definition's query (or a query supplied inline, with no
  saved definition at all) directly against the live model, with no diagram involved. This is
  what `artifact_query_viewpoint`'s `execute` action and the GUI's table/matrix/diagram
  execution views do. In the GUI a query and **any supported presentation** can be composed
  and executed together as a complete, unsaved viewpoint through the **Query model** page
  (below) — anonymous execution uses the same evaluation and presentation semantics as a saved
  definition, and persists nothing.

&nbsp;

## The Query model page: compose and run without saving

The GUI's **Query model** page (`/viewpoints/query`, reached from the "Query model" button on
the Viewpoints page) lets anyone compose and run a complete viewpoint — a **Query** and a
**Presentation** — without creating any artifact:

- **Query** and **Presentation** tabs reuse the same builders the saved-viewpoint editor uses;
  the reduced page deliberately omits identity, tier, versioning, and stakeholder/concern fields.
- **Run** validates the current draft, prompts for any required parameters (recorded in the
  execution's provenance), and shows the result in the selected representation — **exploration,
  table, matrix, or diagram**, all four reachable from the same unsaved query + presentation.
  Changing the presentation re-runs the same query through the new representation without
  discarding query state; editing after a run marks the visible result **stale** until the next
  successful Run.
- **Non-persistence:** running an ad-hoc query writes nothing — no `.arch-repo/viewpoints.yaml`
  entry and no persistence dry-run. The whole flow is available with **read-only** access; only
  **Save as viewpoint…** is write-gated.
- **Save as viewpoint…** carries the composed query + presentation into the full
  `/viewpoints/new` editor so a write-access user can add identity fields and persist it as a new
  definition; nothing is written until they complete and save.

**Ephemeral presentation override on a saved viewpoint.** On a saved viewpoint's result page,
"View as… (unsaved)" re-executes the saved *query* under a different presentation
(exploration / table / matrix / diagram) for this view only — issued as `slug + presentation`,
writing nothing and never mutating the stored definition (available in read-only mode). Returning
to the default clears the override and shows the saved presentation; a write-access user can then
Save-as a new definition. Omitting `presentation` with a slug uses the saved definition's own
presentation, and existing query-only clients (including MCP) are unaffected.

&nbsp;

## Applying a viewpoint to an existing diagram or matrix

Set a `viewpoint:` block in a diagram or matrix's frontmatter (`slug`, `version`, and
optionally `enforcement_override`) to pin it to a definition. Every placed entity and
connection is then classified against that definition:

- **Fully matching** (in scope, satisfies the query) — rendered normally, and styled per the
  definition's style rules if it has any.
- **Out of scope** — the entity/connection type isn't in the definition's scope at all.
- **Criteria mismatch** — in scope, but fails the query's criteria (only checked when the
  definition has a query).
- **Endpoint excluded** — a connection whose source or target is itself excluded.

The **enforcement setting** (`off | warn | ghost`, defaulting to `warn`, overridable per
application) decides what happens to non-matching items:

| Enforcement | Non-matching items |
|---|---|
| `off` | Rendered normally — no ghosting, no reasons reported. |
| `warn` | Rendered normally, but the reason is recorded and surfaced (verifier warning, GUI badge). |
| `ghost` | Visually de-emphasized (or, with the GUI's "hide instead of ghost" toggle, hidden). |

Styling never applies to an excluded item, in any enforcement mode — a ghosted element
wearing a highlight color would contradict its own exclusion. A pinned version older than
the definition's current version is a **stale pin**: the diagram is still evaluated against
the *current* definition (no old versions are retained), with a distinct warning rather than
a silent reinterpretation. An unknown viewpoint slug is always an error, never silently
ignored.

The verifier (`artifact_verify` and every write path) checks a diagram's `viewpoint:`
application on every run, using the exact same evaluation the GUI's ghost/hide overlay uses
— a CI check and what a human sees in the browser can never disagree:

| Code | Severity | Meaning |
|---|---|---|
| E180 | error | Unknown viewpoint slug. |
| W180 | warning | Pinned version is older than the definition's current version. |
| W181 | warning | A placed entity/connection is out of the definition's scope. |
| W182 | warning | A placed entity/connection is in scope but fails the definition's query. |

&nbsp;

## The criteria model

A viewpoint's `query` selects entities (and, through them, connections) with a **criteria
tree**: `AND`/`OR` groups of conditions, each optionally negated. Every condition compares one
attribute (a reserved read-model field like `type`/`status`/`group`, or a repo-specific
attribute from that entity's effective schema) against a value using a comparator (`eq`,
`neq`, `in`, `exists`, `absent`, `lt`, `lte`, `gt`, `gte`).

**Ranked attributes.** Some attributes are rated on a scale whose order matters but whose steps
are not measurable — a severity of `negligible … catastrophic`, a TLP level. Their schema marks
the value list as ranked (`x-scale: ordinal`), which makes `lt`/`gt` order them **by rank rather
than alphabetically**: `impact gt minor` matches `catastrophic`, where a plain string comparison
would not. `min` and `max` then pick the highest- or lowest-ranked member, while totals and
averages over them are refused — the gap between `major` and `catastrophic` is not a known
quantity, so averaging them would produce a number that reads as precise and means nothing.
Ranks belong to one value list, so ordering a severity against a likelihood is refused too. See
[Ranked attributes](../reference/viewpoints-schema.md#ranked-attributes-x-scale-ordinal).

**A simple filter** — every application component:

```yaml
query:
  entity_criteria:
    kind: group
    conjunction: and
    children:
      - {kind: condition, attribute: type, comparator: in, value: [application-component]}
```

**Nested boolean logic with negation** — active elements, in either the application or
technology domain, that are *not* deprecated:

```yaml
query:
  entity_criteria:
    kind: group
    conjunction: and
    children:
      - kind: group
        conjunction: or
        children:
          - {kind: condition, attribute: domain, comparator: eq, value: application}
          - {kind: condition, attribute: domain, comparator: eq, value: technology}
      - {kind: condition, attribute: status, comparator: eq, value: deprecated, negate: true}
```

Negation is the strict logical complement — "not deprecated" also matches an entity with no
`status` set at all, since "has no value" is not "equals deprecated" either. Missing
attributes match only the `absent` comparator; every other comparator treats a missing
attribute as no match, before `negate` is applied.

**A relational predicate** — this is where viewpoints go beyond a flat filter. An
`IncidentConnectionCondition` matches an entity that has (or, negated, does not have) at
least one incident connection satisfying criteria on *both* legs of the hop — the connection
itself, and the entity on the other end:

```yaml
query:
  entity_criteria:
    kind: group
    conjunction: and
    children:
      - {kind: condition, attribute: type, comparator: eq, value: application-component}
      - kind: incident
        direction: outgoing
        connection_criteria:
          kind: group
          conjunction: and
          children:
            - {kind: condition, attribute: type, comparator: eq, value: archimate-serving}
        endpoint_criteria:
          kind: group
          conjunction: and
          children:
            - {kind: condition, attribute: type, comparator: eq, value: process}
```

"Application components that serve at least one process." Add `include_connected` (a
**neighbor inclusion**) to widen the result to include those served processes too, as
context — the complement of the incident condition: an incident condition *filters* (narrows
which entities match), a neighbor inclusion *widens* (adds entities connected to the primary
result). Included neighbors carry `membership: expanded` rather than `primary`, so a surface
can render them distinctly.

A connection appears in the result only when **both** its source and target entities are
included (primary or expanded) — this is a fixed evaluator rule, not something a query can
override. `connections.criteria` narrows *within* that structural set (e.g., "only serving
connections with `strength >= 3`"); it can never widen past it.

&nbsp;

## Parameters: the same definition, different anchors

A definition can declare typed **parameters**, filled in at execution time rather than
baked into the saved query. This is what turns "what depends on this specific component"
into one reusable definition instead of one hand-authored viewpoint per component:

```yaml
query:
  parameters:
    - {name: anchor, type: entity-id, required: true, description: The element whose impact is analyzed}
  entity_criteria:
    kind: group
    conjunction: and
    children:
      - {kind: condition, attribute: id, comparator: eq, value: {from: parameter, name: anchor}}
```

Parameter types are `string`, `integer`, `number`, `date`, `boolean`, `slug`, or `entity-id`
(the last resolved through the same entity picker used everywhere else in the GUI, never a
free-text id field). A required parameter with no supplied value is a typed
`ViewpointParameterError`, never a silent empty result — the GUI prompts for it before the
first execution rather than letting it fail once and report an opaque error. See the
`element-dependents`/`element-dependencies` definitions for a worked example (an
`anchor` parameter feeding a `derived`, `incoming`/`outgoing` neighbor inclusion).

&nbsp;

## Bindings: comparing against another selection

A **binding** names a second, independent selection — entities or connections — that the
primary query can then compare against, without a second saved viewpoint or a formula
language. Every binding declares its `select` (`entities` or `connections`), a `criteria`
tree exactly like the primary one, and an explicit `result_type` (`entity[type]` /
`entities[type]` / `connection[type]` / `connections[type]` / `scalar`) — checked statically,
so a condition that references a binding the wrong way (comparing a set where a scalar is
expected, say) is a validation error at save time, not a runtime surprise.

**Application components that serve at least one requirement** — a binding selects the
requirement population, and an incident condition checks membership against it via
`in`/`{from: binding, ...}` (the same value-reference kind a literal or a parameter uses):

```yaml
query:
  bindings:
    - name: open_requirements
      select: entities
      criteria:
        kind: group
        conjunction: and
        children:
          - {kind: condition, attribute: type, comparator: eq, value: requirement}
      result_type: entities[requirement]
  entity_criteria:
    kind: group
    conjunction: and
    children:
      - {kind: condition, attribute: type, comparator: eq, value: application-component}
      - kind: incident
        direction: outgoing
        endpoint_criteria:
          kind: group
          conjunction: and
          children:
            - {kind: condition, attribute: id, comparator: in, value: {from: binding, name: open_requirements, project: id}}
```

An entity-selecting binding (`select: entities`) and a connection-selecting binding
(`select: connections`) are visibly distinct everywhere a binding can be referenced — the GUI
labels each accordingly, and a `ValueRef` picker only offers bindings whose result type is
compatible with the comparator in play. `in`/`not_in` require a *list* result type
(`entities[...]`/`connections[...]`, the plural forms); a scalar (`entity[...]`) binding
projects a single comparable value instead.

&nbsp;

## Derived attributes: item-scoped facts about the result

A **derived attribute** computes one extra fact per matched item — a count or an aggregate
(`sum`/`avg`/`min`/`max`) over its incident connections/endpoints, or over
`relationship.hops` (the shortest derived-relationship distance to a related selection) —
referenceable from styling-rule criteria and range bands as `derived.<name>`, without a
second query:

```yaml
query:
  derived:
    - name: hop_distance
      traversal: derived        # relationship.hops only makes sense over derived traversal
      reduce: min
      of: relationship.hops
presentation:
  styling_rules:
    - capability: node_color
      mode: range
      range_attribute: derived.hop_distance
      range_bands:
        - {minimum: null, maximum: 3, value: color-ok}
        - {minimum: 3, maximum: null, value: color-warn}
```

`reduce` defaults to `count` (no `of` needed — it just counts matching connections or
endpoints); any other reduction requires `of`. Table `columns` currently resolve against the
entity attribute schema only — a derived attribute isn't yet a column source, only a styling
input.

Derived attributes referenced by the query's own criteria (filtering on a count, say) are
computed eagerly, before the primary result is even assembled; attributes used only for
display are deferred until after filtering, against the retained population only — this
split is what keeps a derived-attribute-heavy definition fast on a real repo rather than
computing every attribute for every candidate up front.

&nbsp;

## Traversal: direct vs. derived, certain vs. potential

Every place a query looks at connections — the primary `incident` predicate, a neighbor
inclusion, `connections`, or a `relationship.hops` derived attribute — takes a `traversal`
mode:

- **`direct`** (the default) — only a single, explicitly modeled connection counts.
- **`derived`** — an indirect relationship, composed transitively across intermediate
  elements per the ArchiMate derivation rules, counts too. See
  [Impact analysis](impact-analysis.md) for what "derived" actually means and how certain vs.
  potential derivations are distinguished.

`derived` traversal also takes `include_potential` (whether lower-confidence derivations
count, default `false`) and an optional `max_hops` bound. A derived-relationship search that
would otherwise run unbounded stops gracefully at a wall-clock time budget and returns its
genuine partial result flagged in the response's `warnings` — never a silent truncation, and
never an error for what is, in a large repo, an entirely ordinary result.

&nbsp;

## Scope-only execution

A definition with `scope` but no `query` is still executable — the scope fallback derives an
implicit "everything admissible by scope" query automatically, so a starter definition
authored before its criteria are worked out (or one that genuinely only needs "every
application component," nothing more) never shows a blank pane. The GUI's Query tab makes
this explicit rather than silently blank: *"Scope-only viewpoint — executes via its concept
scope. Add a query to refine."*

&nbsp;

## Worked examples

Runnable today against this repository's own self-model, via `artifact_query_viewpoint`
(MCP) or the GUI's Viewpoints page:

- **`element-dependents`** — "what is affected if ⟨anchor⟩ changes": a parameterized,
  `traversal: derived` impact query (see [Impact analysis](impact-analysis.md)).
- **`business-technology-support`** — "which business roles and services does this
  technology indirectly support": business domain as the primary selection, technology as a
  `derived` neighbor inclusion, skipping the intervening application layer — the "reduce
  clutter" pattern for a cross-domain question, rather than one flat multi-domain dump.
- **`goal-realization`** / **`motivation`** — plain domain-and-type filters, no traversal at
  all, for the simplest end of the spectrum.

&nbsp;

## The four representations

| Representation | Shows | Styling capabilities |
|---|---|---|
| `exploration` | Graph navigation over the matched population | node shape/icon/color, edge color/emphasis, cluster grouping |
| `table` | A flat list, one row per matched entity, with `columns` projecting attributes | columns, badges, sort, row grouping |
| `matrix` | A relationship grid between two entity populations | row/column axis, cell emphasis |
| `diagram` | An ad-hoc ArchiMate-notation rendering — same rendering engine as a real diagram, but never persisted and needs no `ViewpointApplication` | node/edge color, edge emphasis, cluster grouping (fixed notation — shape/icon aren't overridable here) |

A matrix has two axis modes: **grouped** (`row_by`/`column_by` split one population by a
type/specialization/group key — the traditional relationship-matrix shape) or **criteria**
(`row_criteria`/`column_criteria` define two independent entity populations — requirements ×
components, stakeholders × concerns — for a disjoint-population matrix). The two modes are
mutually exclusive on one definition.

&nbsp;

## Styling: match mode and range mode

`styling_rules` are evaluated in order, first match wins per capability, falling back to
`default_style`:

- **`mode: match`** — reuses the exact same criteria-tree type as query filtering, so a style
  rule can express "highlight this entity when it has a connection matching Y to an entity
  matching Z" with no separate mechanism.
- **`mode: range`** — a numeric/date attribute mapped through explicit, non-overlapping
  half-open bands (`[minimum, maximum)`) to a style token — the threshold/gradient case
  (e.g., risk score → ok/caution/danger).

Legends are always derived from `styling_rules` + `range_bands` + `default_style` — there's
nothing to separately author.

A shipped example of range-mode styling: the **Resource Map** viewpoint (ArchiMate's
strategy-layer example viewpoint) carries a heat-map rule over a repo-defined
`investment_level` profile attribute (1 low – 5 high), so resources render banded by
investment once a repository defines that attribute — and in the default style when it
doesn't. Its sibling **Capability Map** deliberately ships *no* heat-map rule: the
ArchiMate text allows one over an investment attribute, but styling an attribute no
repository has defined would color everything by absence, so the rule is left to the
repository that defines the attribute. Executing either viewpoint against this
repository's own model shows the difference.

&nbsp;

## Authoring a definition

Three equivalent surfaces write the same catalog file and run the same validation:

- **GUI** — the viewpoints management view builds a definition through structured fields
  (identity, criteria groups, connection selection, presentation) rather than hand-written
  YAML, and previews the plain-language summary live as you edit.
- **MCP** — `artifact_viewpoint` (`arch-repo-write`), actions `create`/`edit`/`delete`. The
  `definition` parameter is the full Appendix-A mapping; see
  [Viewpoints — schema reference](../reference/viewpoints-schema.md) for the grammar, or ask
  `artifact_help` for the `viewpoints` topic directly.
- **Direct YAML** — hand-editing `.arch-repo/viewpoints.yaml`. This is the one path that only
  gets *load*-time validation (structural correctness; registry drift is a warning, not a
  rejection) rather than the fuller save-time checks the GUI/MCP path enforces — see
  [Lifecycle & validation](../reference/viewpoints-schema.md#lifecycle--validation).

![The Query tab of the Element Dependents viewpoint: a required `anchor` parameter of type entity-id, a condition matching `id` against that supplied parameter, and an `impact-distance` derived attribute computing the minimum hop count over incoming relationship-derived connections](../media/viewpoint-query-tab.png)

The Query tab above is the *Element Dependents* definition — impact analysis. It shows the
grammar doing the three things prose about it tends to describe abstractly: it declares a
parameter (`anchor`, an entity id, required), consumes that parameter in a condition rather
than hard-coding an element, and derives a per-item value (`impact-distance`) from the
candidate's own neighbourhood. Nothing here is YAML the author had to spell; every clause is
a structured field that validates as it is entered.

Module-shipped and enterprise-tier definitions are read-only from an engagement context; open
one via **Customize…** in the catalog, adjust it, and keep your version with **Save as…** —
this records fork lineage (origin slug, version, and content digest), so the catalog can flag
the fork as stale the moment its origin changes. An engagement repo authors its own
definitions in its own `.arch-repo/viewpoints.yaml`. An edit
that changes `scope`, `query`, `presentation`, or `representation_types` requires a version
bump (enforced, not left to author discipline) — that's what makes the stale-pin warning
(W180) meaningful. Deleting a definition is blocked while any diagram/matrix still applies
it; detach those applications first.

Every MCP `artifact_query_viewpoint` `list` entry and every `create`/`edit` response through
`artifact_viewpoint` carries a **plain-language `query_summary`** — the same renderer behind the summary the GUI
editor shows beside the query builder (and its **Test run** results) — so an agent (or a
person reading raw YAML) sees what a viewpoint *means*, not just its structure.

---

*Next: [Impact analysis →](impact-analysis.md)*
