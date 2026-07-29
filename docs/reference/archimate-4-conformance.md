# ArchiMate 4.0 Conformance

This page states what this implementation supports for each requirement in the ArchiMate
4.0 specification's conformance section, and in which implementation-defined manner. Where
a behavior is already documented elsewhere in these docs, this page links there instead of
repeating it. It is not a usage guide; see the linked pages for how to use any of this.

> The model aims for conformance with the **ArchiMate 4.0** standard; conformance has not
> been independently verified, so no conformance claim is made. The Open Group's own
> conformance section lists six requirements for an implementation; each is described
> below, followed by the exchange-format requirement (§7) that the Open Group's
> product-conformance requirements state separately from the language specification.

&nbsp;

## 1 — Language structure, relationships, domains, and cross-domain dependencies

The `archimate-4` ontology module (`src/ontologies/archimate_4/`) ships 45 entity types
across every domain the standard names — Motivation, Strategy, Business, Application,
Technology, and Implementation & Migration — plus the cross-layer "Other" elements
(Location, Grouping, and the And/Or junctions).

Several concepts the standard generalizes across layers (Service, Process, Function, Event,
Role, Collaboration) are modeled as **one base type each**, differentiated by layer through
an ArchiMate 4 specialization slug (`business-service`, `application-service`,
`technology-service`, …) rather than three duplicate types — a direct implementation of the
standard's own Common Domain generalization, not a shortcut around it. See
[Ontology modules](../05-extensibility/ontology-modules.md) for the module structure and
[Specializations](../05-extensibility/ontology-modules.md#specializations) for how a
layer is assigned.

Relationship-end **multiplicity** uses that exact term (renamed from "cardinality" for
terminology alignment with the standard); see the [CLI & backend](cli-and-backend.md)
deprecation note for the migration path from the old field name.

&nbsp;

## 2 — Standard iconography

40 dedicated SVG glyphs (`tools/gui/src/ui/lib/archimateGlyphs.json`) drive both the GUI's
entity rendering and the generated PlantUML diagram notation, following the standard's
shapes (the role banner, the rounded service pill, the process arrow, the function block,
the notched event, the motivation glyphs, …). A specialization without its own dedicated
glyph renders as a guillemet stereotype badge on its base type's shape — `«Business
Collaboration»`, e.g. — never a generic unlabeled box. See
[Diagramming](../03-modeling/diagramming.md) for the rendering pipeline and
[Specializations → Rendering](../05-extensibility/ontology-modules.md#rendering) for the
stereotype-badge rule.

&nbsp;

## 3 — The viewpoint mechanism

A `ConceptScope` primitive (entity types + connection types + a criteria tree) is the one
thing diagram-type filters, binding admissibility, and viewpoint scope all compile to.
`ViewpointDefinition`s are versioned and either module-shipped (the Appendix-C example
viewpoints plus a few tool-specific impact-analysis ones — see §6) or repo-authored;
`ViewpointApplication`s pin a diagram to a specific definition version, non-destructively
(`off`/`warn`/`ghost` enforcement, never a hard block), and flag drift the moment the pinned
version and the diagram's actual content disagree. Four representations — table, matrix,
diagram, and graph exploration — read the same scope. See
[Viewpoints](../03-modeling/viewpoints.md) for the full concept and how-to, and
[Viewpoints — schema reference](viewpoints-schema.md) for the declaration grammar and the
`artifact_viewpoint`/`artifact_query_viewpoint` MCP tools.

**Indirect relationship handling.** A viewpoint's `traversal: derived` mode computes a new
*derived* relationship across a chain of real ones, per Appendix B's derivation rules — not
only the weaker path-based projection (`src/application/derivation/path_projection.py`,
still used for the persisted-diagram generation flow) that merely finds and displays an
existing chain. Every default-parameterized impact-analysis viewpoint
(`element-dependents`/`element-dependencies`), the ad-hoc layered-exploration flow, and the
`artifact_query_find_neighbors` MCP tool are built on this computation. See
[Impact analysis](../03-modeling/impact-analysis.md) for the concept and how-to.

&nbsp;

## 4 — Language customization mechanisms (implementation-defined)

Customization is **concept-level**: one unified specialization catalog covers both entity
and connection types (`concept_kind: entity | connection`), enumerated in
`specializations.yaml` at two tiers — a module-shipped informative library (names and
notation only, license-clean) and a repo-level extension (`.arch-repo/specializations.yaml`,
enterprise baseline / engagement superset, enforced at promotion). A specialization may
narrow — never widen — what its parent type permits (`restrict_relationships`,
`restrict_endpoints`). Attribute constraints compile 1:1 from a specialization's own inline
`attributes:` (or an attached schema file) into a JSON Schema fragment — a specialization
and its profile are one concept, not two; a profile is never independently reusable or
shared across specializations. See
[Ontology modules → Specializations](../05-extensibility/ontology-modules.md#specializations)
for the full mechanism and
[Attribute profiles & frontmatter schemata](../05-extensibility/schemata-and-profiles.md)
for the compiled-schema shape.

Separately, **authoring guidance** (`create_when`/`never_create_when` prose per type) is a
deployment-level, license-gated import (`arch-import-guidance`) layered over this
mechanism — an authoring aid, not itself part of the standard's customization requirement.

&nbsp;

## 5 — Relationship rules (Appendix B)

125 permitted `(source type, target type, relationship type)` rows drive both authoring-time
validation and the GUI's relationship picker (`src/ontologies/archimate_4/connections.yaml`,
`src/domain/relationships/permitted_relationships.py`). One deliberate correction from the informative
pre-release snapshot this ontology started from: per the final published standard's
§5.1.2, **composition is permitted everywhere aggregation is** — verified by diffing the
two relationship types' permitted rows directly, with a standing structural test
(`composition permitted ⊇ aggregation permitted`) that fails if a future rule addition ever
regresses it.

Appendix B's **derivation rules** (DR1–DR8, certain; PDR1–PDR12, potential) are implemented
as an executable engine (`src/domain/relationships/relationship_reachability.py`,
`src/domain/relationships/relationship_derivation.py`), not a static table — every real chain of
connections in a repository is a candidate for composition at query time. The rules' behavior
is exercised by these test modules under `tests/domain/` (test coverage of the
implementation, not independent conformance verification):

| Method | Test module |
|---|---|
| Per-rule certain-composition behavior (DR1–DR8) | `test_relationship_derivation_rules.py` |
| Per-rule potential-composition behavior (PDR1–PDR12) | `test_relationship_derivation_potential.py` |
| Independent dual encoding of the rule table, checked cell-by-cell against the engine | `test_relationship_derivation_dual_encoding.py` |
| Exhaustive metamodel-wide composition sweep from every direct-relationship pair | `test_relationship_derivation_exhaustive.py` |
| Encoding-independent semantic invariants (role/strength ordering, the direct-model boundary, the PDR12 grouping-does-not-block-derivation guard) | `test_relationship_derivation_invariants.py` |
| Admissibility restrictions (R1–R14, RJ1–RJ2) | `test_relationship_derivation_restrictions.py` |
| The spec's own worked examples (B-3, B-9, B-11, B-12, B-17), executed against the real engine, not hand-traced | `test_relationship_derivation_worked_examples.py` |

Association is deliberately excluded from further derivation composition (weakest dependency
type, no directional semantics to propagate) — it can still be the outermost relationship a
stronger chain composes *onto*, just never a link composed *across*. See
[Impact analysis → Composing relationships](../03-modeling/impact-analysis.md#composing-relationships-role-and-strength)
for the full role/strength table.

&nbsp;

## 6 — Example viewpoints (Appendix C) — optional

The module ships 28 `ViewpointDefinition`s (`src/ontologies/archimate_4/viewpoints.yaml`), 25
of them transcribed from a specific Appendix C table (Application Cooperation/Structure/
Usage, Capability Map, Goal Realization, Implementation & Deployment/Migration, Information
Structure, Layered, Migration, Motivation, Organization, Outcome Realization, Physical,
Process Cooperation, Product, Project, Requirements Realization, Resource Map, Service
Realization, Stakeholder, Strategy, Technology, Technology Usage, Value Stream). The standard
marks this requirement optional (**"may support"**). Each transcribed definition's
purpose/content/stakeholders/concerns/scope is checked against its source table
cell-by-cell in `test_default_viewpoint_library_spec_fidelity.py`;
`test_default_viewpoint_library.py`/`test_default_viewpoint_library_common_types.py` cover
the remaining membership/type-usage properties. The three non-table entries
(`element-dependents`/`element-dependencies`/`process-technology-support`) are this
implementation's own tool-specific impact-analysis capability, documented as such in their
own `description`, not presented as part of the standard. The viewpoint mechanism is open to
repo-authored definitions beyond this starting set.

&nbsp;

## 7 — Model exchange

The exchange file format is specified in a separate Open Group standard (C19C) rather than
in the language specification's conformance section, but the Open Group's
product-conformance requirements make supporting it a requirement of its own: "each
conforming product shall support the ArchiMate Model Exchange File Format" (published for
ArchiMate 3.0 — the most recent revision of that document at the time of writing).

C19C v3.1 model-exchange import/export is available via the `arch-exchange` CLI: import
applies the standard's Appendix E.4 migration table (3.x layer-specific types → the
ArchiMate 4 base type plus specialization); export inverts it. Composition is never
downgraded to association on either path, and every unmapped or out-of-scope item is
reported by kind and reason, never silently dropped. See
[Model exchange](cli-and-backend.md#model-exchange) for usage.

---

# Roadmap (not conformance)

Potential future tooling directions. None is an ArchiMate 4.0 requirement; they are recorded
here, separate from the conformance material above, and the query/presentation split in the
underlying model is intended to accommodate them later:

- A fuller presentation-rule engine — label/tooltip rules and attribute-driven heat maps
  beyond the current match/range/scale styling.
- Saved executions as their own persisted view artifacts, rather than the ephemeral
  table/matrix renderings executions produce today.
- Dedicated catalog/report view artifact kinds.

---

*See also: [Ontology modules](../05-extensibility/ontology-modules.md) ·
[Interfaces & MCP](../03-modeling/interfaces-and-mcp.md) ·
[CLI & backend](cli-and-backend.md)*
