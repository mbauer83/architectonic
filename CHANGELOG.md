# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [0.7.1] — 2026-08-25

**[Full detail → `changelog-assets/0.7.1-detail.md`](changelog-assets/0.7.1-detail.md)**

**Fixes for cases where the product stated one thing and did another** — a diagram drawing fewer steps
than its model declares, an audit archive silent about the operation that empties it, a preview that
wrote, and findings computed and then withheld from every reader entitled to them.

### Fixed

- **An activity diagram draws every step its model declares, exactly once.** Four causes, from a step
  two branches reach to a graph containing a loop.
- **A declared step the stored body does not draw is reported (W045)** — every rule read the model and
  none the picture; `puml="auto-sync"` answers it.
- **A swimlane header selects its lane**, as an action, a decision and a partition already did — the
  renderer emitted the anchor and the viewer resolved none of it.
- **A decision whose merge edge names its own branch is reported (W047).** It draws that step, and
  everything after it, twice.
- **`connection-ids-used` records the connections a diagram draws, and no others.** An edit replacing
  the body kept the old references, and that surface answers which views show a connection.
- **A relation `connection-ids-used` lists but the body does not draw is reported (W307).** On a
  hand-edited diagram the wrong claim never heals.
- **An `artifact` may be assigned to any technology host.** The table permitted ArchiMate's deployment
  relation into an `artifact` from nothing at all; the aggregation path is still read.
- **A deployment host is drawn as a node whether or not anything is drawn inside it.** A host holding
  nothing fell through to the generic container shape — a volume rendered as a deployed application.
- **A container deployed on more than one host is drawn inside the host a view is showing.** One
  placement was kept per container, by id order, so a narrowed view could lose the container.
- **Replacing the assurance graph is recorded in the audit archive.** `import` and `seed` empty the
  store and appended nothing; one entry now lands in the same transaction.
- **An analysis with no architecture anchor can be given one.** Optional at creation and immutable
  afterwards left no route. Moving or clearing one is still refused (`anchor_immutable`, HTTP 409).
- **A factor judgement cannot be recorded against a basis that was never assembled.** Its digest was
  a hash no reader holding the model would compute.
- **An element inside an analysed controller is no longer reported as unanalysed (W511).** Containment
  carries that finding's control-structure half, not its per-component failure-mode half.
- **Coverage findings reach the API and the GUI.** The exposure filter kept an issue only when its
  subject was an assurance node, and every coverage finding names an architecture element.
- **A constraint answered by argument is no longer asked for evidence of a control.** An
  `alarp-justified` constraint argues that residual exposure is as low as reasonably practicable;
  there is no control whose working could be evidenced.
- **A `format` facet says what it accepts** — the `Source Repository` description called it
  informative while the checker refused values.
- **A tag the sanitiser rejects is shown, not deleted** — `projects/<slug>/model/` had rendered as
  `projects//model/`.
- **The security-findings page renders.** Its route mounted the per-entity view with no entity. It
  lists the assessed anchors instead.
- **Search finds a diagram by its title.** Its four indexed columns ranked equally, so a diagram named
  for the query ranked level with one that merely drew something of that name.
- **A scratchpad note is returned for its own words, and only while it is still a thought.** It
  answered any query its *pad's* title matched, kept answering after a lift, and was dropped outright
  when the two repository roots were merged.
- **A search window belongs to the ranking that filled it.** `/api/search` asked for three times its
  limit and re-cut afterwards, spending the round-robin and the minority-kind floor on unseen rows.
- **`artifact_group` honours `dry_run` for every action.** It defaulted to true and was read by one
  branch of one action; the answer now names `dry_run` and `wrote`.
- **Content filed under a group nothing declares is reported (W046).** An artifact created into an
  undeclared project was absent from everywhere a person browses.
- **A part composed by two wholes is reported (E340)** — this ontology defines composition as
  exclusive and no rule enforced it.
- **A batch commit that cannot carry all of its changes publishes none of them** — a staged change
  outside the managed subtrees was dropped after the write said it wrote.
- **A bound element shows what it corresponds to in the model**, as a link, on every diagram type that
  declares one. Two further consumers read a shorthand the persist path strips, so an ArchiMate
  occurrence lost the entity it redraws: the renderer resolved none, the editor saw none as a drawing.

### Changed

- **An ArchiMate grouping is drawn as an open container** — no fill, dashed border — instead of taking
  its domain's colour. It holds other elements, so a fill put a coloured plane behind them.
- **Type checking is deterministic.** `zuban check` reported a type error on roughly four runs in ten
  on an unchanged file: two modules named each other's types. The values now sit in a shared module.

### Known limitation

- A fork whose branches sit in different swimlanes renders with its edges turning against the bar and
  overlapping it; PlantUML's activity layout honours no spacing parameter. And a `step-flow` that
  closes a loop is not drawn — every step of the loop is, which is new, but not the edge back.

### Upgrading

- Nothing to run. A repository whose stored activity bodies have the affected shape starts reporting
  **W045**; `artifact_edit_diagram(puml="auto-sync")` on each named diagram clears it.
- A repository materialised before 0.7.1 holds the older `Source Repository` description; the upgrade
  reports it as an operator customisation and never overwrites it.
- A diagram listing a connection its body does not draw starts reporting **W307**.
  `artifact_edit_diagram(puml="auto-sync")` redraws the edge; removing the entry is right if the
  relation should not be there.
- `arch-repair upgrade` now rewrites the generated `_archimate-*.puml` includes. It never did, so an
  upgraded repository still carried the appearance declarations of whenever it was last initialised.
- On the next `puml="auto-sync"`: a stored activity diagram's lane headers become selectable, and a
  `c4-deployment` view redraws an empty host as a node and rehomes a multi-hosted container.
- An assurance store carries its archive across `seed` and `import`, so the first re-seed after
  upgrading appends an entry. Imports that already happened get none invented for them.
- Three new diagnostics on existing content. **W046**: content under a group its axis does not
  declare — `artifact_group(action="create", target=<slug>)` clears it. **W047**: a decision naming
  its own branch as its merge target — remove the `step-flow` edge or retarget it. **E340**: two
  wholes composing one part, an error that blocks a write — all but one is an aggregation, or wrong.
- `artifact_group` previews by default: a caller relying on `create` writing without an explicit
  `dry_run=False` now gets a report and no change.

## [0.7.0] — 2026-08-17

**[Full detail → `changelog-assets/0.7.0-detail.md`](changelog-assets/0.7.0-detail.md)**

**A document type can now ask for a diagram or another document, not only an entity.** C4 gains the
portfolio altitude above its zoom and a deployment view beside it, and arc42 ships as a template
whose twelve sections say what model content each one expects.

### Added

- **Required and suggested references reach all three vocabularies.** A document type, and a section
  within it, declares terms under `required_connections` and `suggested_connections`. A bare term
  names an entity type, `@class` an element class, `doc:<type>` a document type and
  `diagram:<type>` a diagram type. `doc:@all` and `diagram:@all` mean any of that kind. The
  entity-only spelling is still read, so no schema file has to be rewritten.
- **A term naming a diagram type this deployment does not register is a warning (W159), not an
  error.** The assurance diagram types need the confidential store, and a stored diagram of such a
  type still satisfies the requirement, so a shipped template stays usable on a host that cannot
  create one.
- **C4 System Landscape** — the altitude above a system context. It is scoped by a *set* of systems
  (`_scope_entity_ids`), draws them together with the people and third-party systems around all of
  them, and drills down into the system context of whichever one you click.
- **C4 Deployment** — where one system's containers run. It draws the same containers a container
  view draws, placed on the technology hosting them, so it sits beside the zoom rather than below it,
  and the navigation offers each as a lookup from the other. Hosting is read along ArchiMate's path,
  `technology-node --aggregation--> artifact --realization--> application-component`; a container
  with no artifact is left out rather than given an invented host.
- **A diagram can be bound to several entities at once.** `bindings[].target` accepts `entity_ids`
  beside `entity_id`, which is what a landscape's scope is. A diagram still has at most one
  diagram-level `scoped-by` binding (E405), the plurality is in its target, and an unresolved member
  is **E414**.
- **arc42**, as a document type every repository is scaffolded with: twelve sections in the
  standard's order, each declaring the model content it expects. Only *Architecture Decisions*
  (`doc:adr`) and *Quality Requirements* (`requirement`) require anything, so a skeleton is writable
  the day it is created. Section structure from arc42 by Dr. Gernot Starke and Dr. Peter Hruschka,
  CC BY-SA 4.0, carried on the document type and shown on the create form.
- **`THIRD-PARTY-NOTICES.md` inventories shipped content**, not only dependencies — a new
  "Shipped content" section, generated from `licenses/content.json`.
- **`data-store`, a specialization of `application-component`**, with its own attribute profile:
  source of truth, consistency model, retention, backup and recovery. C4 counts a data store as a
  container, so one the model declares is drawn with the cylinder notation — from the declaration
  rather than from a keyword in the technology string.
- **A grouping is drawn as a C4 group** — a boundary around the elements it holds, rather than an
  element of its own. A group holds one level of abstraction, so members the level does not draw are
  left out, and a group with no drawn members is not drawn.
- **`_direction` on a generated C4 body**, `left_to_right` (the default) or `top_to_bottom`, for a
  view that nests boundaries and hits a GraphViz layout failure.
- **A `format` facet on attribute declarations**, so a value can say what it *addresses*. `uri`
  accepts a reference, absolute or relative; `date` is a calendar date. Both are enforced, and a
  schema declaring a format nothing checks is refused at startup.

### Changed

- **`GET /api/document-types` and the document schemata serve `required_connections` /
  `suggested_connections`** in place of the `*_entity_type_connections` pair, plus `attribution`
  where a type reproduces a third-party template. Repository schema files keep whichever spelling
  they carry.
- **A C4 diagram's navigation carries two axes.** `current_level` orders containment (0 landscape,
  1 context, 2 container, 3 component) and is `null` for a deployment view;
  `deployment_diagrams` and `subject_diagrams` name the other axis in each direction.
  `scope_entity_ids` and `scope_entity_names` accompany the singular fields.
- **A sibling container is drawn with ordinary notation.** Zooming into one container puts the rest
  of the same system outside the frame; the external marker is reserved for software the
  architecture does not own.
- **A dependency edge carries a label only where the label adds something.** Serving and association
  were labelled "uses", which the arrow already says. Flow, triggering and access keep their verbs,
  and an author's `edge_labels` entry is used whatever the type.
- **A C4 view collects a dependency on any part of another drawn element** and raises the edge onto
  the box standing for it. A container whose only relations ran to something nested inside a sibling
  was drawn with no edges at all.
- **A drill-down badge on a container with several component views opens a menu.** Where a container
  is documented one concern at a time, the badge offered no way to say which view was meant.
- **The datatype type catalog reports what each classifier declares itself to be.** Every row
  carried the constant `classifier`, so a repository's own `classifier_kind: primitive` was
  indistinguishable from a structured type. The `kind` filter selects on the declared kind,
  `primitives` lists the built-ins then the repository's own, and the picker offers one beside
  `String` and `Integer`.
- **An authoring input honours a declared format and the declared bounds.** A `date` attribute gets
  a date control, a `uri` attribute a hint and a check, and `minLength`, `maxLength` and `pattern`
  now report — they were served and bound to the control and shown by nothing.

### Fixed

- **An entity-type requirement is no longer satisfied by a linked document or diagram.** The reading
  behind it reported every linked artifact's `artifact-type`, so a linked diagram contributed the
  literal type `diagram` to the set an entity term was matched against.
- **Promotion refuses a selection that would leave a required *document* or *diagram* reference
  dangling**, and names the artifact — as it already did for a required entity. The engagement and
  enterprise schema comparison also compares document-level terms, which it had never done.
- **A diagram whose layout crashes is refused (E350) rather than written**, from every write path.
  An edit used to answer `valid: true` over a picture that was a stack trace. The previous good
  render is kept.
- **No edge is drawn onto a C4 boundary.** A boundary is not an element and cannot be an endpoint of
  a relationship, which holds for the scope wrapper, a group and an occupied deployment node alike.
  The containment is still recorded; only the arrow is declined.
- **A viewpoint result past the renderer's entity ceiling says so on screen**, with the counts and
  what to use instead. The refusal reached the page as a generic failure message.

## [0.6.0] — 2026-08-16

**[Full detail → `changelog-assets/0.6.0-detail.md`](changelog-assets/0.6.0-detail.md)**

**A picture now says what the model says.** Colour and corner shape are declared by the
meta-ontology and drawn the same way everywhere. A graph shows every relationship among the
elements it draws, with a filter — built from the same declarations — to keep that readable.
Three renderers stopped losing content that the source contained.

### Added

- **Colour and corner shape are declarations.** The meta-ontology states one colour per domain and
  assigns each corner style — square for structure, rounded for behaviour, cut for motivation — to
  the element classes its types already carry. Borders and container tints derive from the declared
  colour. Every surface draws from that one statement, so an element looks the same in a rendered
  diagram and in the graph explorer, and a second meta-ontology brings its own palette and
  categories without code changes.
- **`GET /api/ontology/element-appearance`** answers colour per domain and corner style per entity
  type, resolved, so a client renders without knowing the class vocabulary.
- **`GET /api/ontology/classification-levels`** answers how elements and relationships are
  classified, keyed by concept kind, with every level id an opaque string.
- **`GET /api/connections/among`** answers the connections whose endpoints are both in a set of
  entities.
- **A filter for graph exploration**, built from the levels the meta-ontology declares and the graph
  you have loaded. Values are grouped by what they classify and offered only where the loaded graph
  actually has them, so the choices follow exploration. Excluding an element takes its relationships
  with it, and excluding a relationship type removes the elements it leaves with nothing to show —
  except one that had no relationships to begin with, and except the element being explored. The
  collapsed control reports what it is hiding — `Filter · 1 excluded · 22 of 27 shown` — and the
  selection lives in the address, so a filtered graph is a link. A meta-ontology declaring a
  different chain is offered its own levels under its own labels, with no code change. A level's own
  exclusions are offered alongside what is present, so filtering is undoable one value at a time.
- **The graph viewport has the chrome a diagram's has**: fullscreen, a docked sidebar, a floating
  toolbar, blank-space deselection, and a snapshot of the current frame as SVG or PNG through the
  download menu a diagram already carries. Spacing means something in every layout, each frames
  itself, and free exploration opens in radial.
- **A collaboration gathers the roles that participate in it.** Assignment states allocation and
  association states a link; neither states membership.
- **The declarations a legend reads**; the legend itself is not in this release.

### Fixed

- **A filtered graph keeps what is reachable from the element being explored.** A cluster with no
  path back was drawn one ring beyond the farthest connected element.
- **A C4 container or component diagram draws the system's own services inside it**, not with the
  external-system notation.
- **A diagram whose grouping boxes nest can be read back**; it answered its own request with a 500.
- **Deleting a connection reconciles every diagram that draws it**, whichever way that diagram
  spells the connection's endpoints. Reconciling a diagram also names the relations it leaves
  undrawn: a relation added between two elements it already draws no longer goes unreported.
- **The graph's download control has an accessible name.**
- **The graph explorer draws every relationship among the elements it shows.** What is drawn no
  longer depends on the order you expanded in.
- **An `alt`/`else` guard keeps its first word.** Multi-word guards on sequence diagrams were
  written into the source in brackets, which PlantUML reads as link syntax, so `features computed`
  rendered as `computed`. Single-word guards were unaffected, which is why this went unnoticed.
- **A fork's branches end at the join.** Activity diagrams walked every branch to the end of the
  graph instead of stopping where the branches converge, so everything after the join was repeated
  once per branch and nested forks multiplied it. The continuation is drawn once.
- **Every relationship is drawn with the line style it declares.** `archimate-access` declared a
  dotted line and drew a solid one; twelve further types across the assurance and datatype modules
  declared nothing and drew something else. The declaration and the drawing are now derived from
  one another and held equal by a gate.
- **The relationship macros a diagram body may call are generated from the ontology.** Nine of
  twelve ArchiMate relationships had one; a body calling another drew nothing.
- **A diagram takes the colours, corners, glyphs, line styles and label width the renderer states
  today.** A body carries its own copy so the `.puml` renders on its own, and that copy was
  refreshed only when the whole picture was regenerated, so a diagram whose content had not changed
  went on drawing the palette it was authored with. The header is refreshed on every edit, and a
  check reports any diagram that disagrees.
- **A scratchpad's version is the store's.** A client omitting the in-document version drove the
  stored version backwards, after which two writers could each overwrite the other indefinitely
  without either being detected as stale. A save that stores what is already stored is no longer a
  write, so a drag too small to move anything leaves no modified file and invalidates nobody's
  token.
- **A frame's declared domains survive being edited.** Reading a scratchpad and handing it back —
  which the canvas does on every save — erased what each frame declared, so a frame's type picker
  stopped narrowing.
- **A matrix keeps its axes when its body is edited.** Upserting a matrix through the write path
  dropped the entity axes and the connection-type configuration, which no caller could restate.
- **A matrix's axes must name entities that exist**, and its links must resolve. Both are now
  verified.
- **An FMEA factor's justification can be read back.** The rationale a judgement is refused without
  was recorded and then unavailable through every read surface.
- **Relationship markers at the source end are visible.** Graph edges stopped short of the target
  only, so composition and aggregation diamonds and the assignment ball were drawn underneath their
  own node.
- **A custom primitive resolves the same way every time.** Where two share a label, resolution
  followed dictionary order and could refuse a reference an enterprise declaration satisfies.

### Changed

- **Diagram colours.** Every ArchiMate element's fill, border and container tint changes with the
  new declaration. Nothing about a model changes; the pictures are re-rendered.
- **What a document's prose refers to has one reading.** Four readings of the same markdown link
  disagreed; the one in the cascade-delete preflight could not see a link into a section, so a
  document linking to part of an entity was invisible to the check that finds what a deletion
  breaks.

## [0.5.4] — 2026-08-13

**[Full detail → `changelog-assets/0.5.4-detail.md`](changelog-assets/0.5.4-detail.md)**

**Containment survives the picture.** An element drawn in two containers no longer loses one of
them, and a containment the notation cannot nest is drawn as the relation it is.

### Fixed

- **An element with two containers is drawn once, and the containment that cannot be nested is drawn
  as an arrow.** PlantUML containment is a tree: a second `as ALIAS` is read as a *reference* to the
  element already declared. So an element aggregated by two parents was built inside the first, the
  second container rendered **empty**, and that containment left the picture — while `artifact_verify`
  accepted the body, because every id in it still resolves. The duplication was recursive: a
  twice-parented element took its whole subtree with it. Nesting remains the default, and what cannot
  be nested is now drawn as its own typed arrow.
- **A containment cycle no longer empties a diagram.** With A aggregating B and B aggregating A,
  every element counted as nested and none was left to declare, so the generated body held no
  elements at all. An element aggregating itself did the same.
- **Composition and aggregation draw their ArchiMate diamond** where nesting cannot draw the
  containment — a second parent, a cycle, or a member an authored group has claimed. Both types
  declare a diamond in `notation` and both spelled `puml_arrow: "-->"`, so the graph canvas drew the
  diamond and the diagram drew an anonymous arrow. `notation` is now honoured by every ontology
  loader rather than the ArchiMate one alone, which is why `dt-aggregation` and `dt-composition` drew
  their diamond in a diagram but not in the graph.

### Added

- **`artifact_verify` refuses a body that declares an alias twice (E318).** An error rather than a
  warning: PlantUML reads the second declaration as a reference, so the container it opens renders
  empty and the containment it draws is lost with nothing to see. Scoped to bodies written in the
  element-declaration vocabulary — a diagram type that owns its entity types carries prose that no
  reading of `as ALIAS` can tell from code.

### Changed

- **One insertion of a direction into a PUML arrow token**
  (`application.puml_arrow_tokens`), replacing three that had each been written against the arrow
  forms in use at the time. All three left the containment forms `o--` and `*--` undirected, so a
  composition or aggregation arrow lost its layout rank on both the render and the layout-optimiser
  paths.

## [0.5.3] — 2026-08-12

**[Full detail → `changelog-assets/0.5.3-detail.md`](changelog-assets/0.5.3-detail.md)**

An ArchiMate view that draws a junction could not be authored. Nothing changes an API or a contract.

### Fixed

- **A diagram body may decorate a declaration, and the diagram it writes still verifies.** A junction
  is drawn as a coloured circle (`circle " " as JNA_x #252327`), and the reader that derives
  `entity-ids-used` required the alias to *end the line* — so the junction was dropped from the
  frontmatter while the verifier, resolving drawn aliases another way, refused the diagram for omitting
  it (**E315**). Not a junction problem: a coloured `rectangle` failed identically, and the renderer
  itself appends a colour for any entity carrying a specialization notation. Two latent defects went
  with it — a coloured *container* declaration was read as neither container nor leaf, losing its
  nesting, and a coloured grouping-open lost its label.
- **`artifact_create_diagram` no longer discards an `entity_ids` passed alongside a `puml` body.** It
  routed on `entity_ids and not puml`, so ids the caller named were silently dropped in either id form,
  and nothing said the diagram could not verify. Membership is now honoured and merged with what the
  body infers.

### Changed

- **One reading of what declares a PUML alias** (`application.puml_alias_declarations`), replacing five
  that disagreed about trailing decorations, about whether a hyphen belongs to an alias, and about
  whether quoted prose can look like one. The tolerant reading already existed in one of the five.
- **Every syntax this project reads now has a registered owner**
  (`tests/architecture/test_each_syntax_has_one_reader.py`). The same class of defect had been fixed
  three times, each as an instance with its own test, and between them they enumerated nothing — so a
  fourth had nowhere to be a missing row. Four syntaxes are registered, and the register immediately
  found eight second readers of the connection-declaration section — the syntax every connection in
  the model is written in. **Three are converted here**: the verifier's shape check no longer accepts a
  header its own parser declines, and two more stop hand-rolling the multiplicity stripping the parser
  already does. Five are exempt, shrink-only and each with a reason — three *rewrite* files (cascade
  delete, promotion retarget, cleanup) and need primitives the owner does not expose yet.
- **One reading of how a connection may be named**, and the register found the worse half of it. Three
  functions parsed `source type → target` into a three-string tuple, and two of them had **target and
  type transposed** — a caller moved between them would have swapped the fields with nothing to catch
  it, since both type-check and both read correctly. They also disagreed on `split` versus `rsplit` and
  on stripping. `artifact_id.parse_connection_reference` now answers a `ConnectionReference` record, so
  the transposition is unspellable rather than merely fixed.
- `AGENTS.md` states the rule the register serves: name the owner before writing a parser, and where the
  project both writes a syntax and reads it back, test the pair — over what the syntax permits, and
  verified against the old behaviour before it is trusted.

## [0.5.2] — 2026-08-12

**[Full detail → `changelog-assets/0.5.2-detail.md`](changelog-assets/0.5.2-detail.md)**

Nothing here changes an API or a contract. Two observable behaviours do change, both about what the
product does when something it depends on goes away: a stdio bridge whose backend stopped now answers
and exits instead of hanging, and a backend's log is bounded instead of growing without limit. Every
item was reproduced before it was fixed.

### Fixed

- **A stdio MCP bridge whose backend goes away answers its pending calls and stops.** Measured before:
  a `tools/list` issued after the backend stopped got **no answer for 45 s** and the bridge was still
  running — no reply, no error, no EOF, so a client had nothing to react to. That is the five-hour park
  observed live. Measured after: a JSON-RPC `CONNECTION_CLOSED` (-32000) naming the reason, in 10 ms,
  then exit status 3 so the client relaunches a bridge that re-runs its health and workspace-identity
  checks. The reported cause was wrong about the mechanism — the transport failure never reaches the
  read stream — which is why the reproduction came first.
- **A fetch against an unreachable remote is deferred instead of retried every minute.** Doubling from
  the poll interval to a ceiling of half an hour, and one success clears the record. Twenty minutes of
  a failing origin costs five attempts rather than twenty, and git's stderr is carried once per episode
  instead of six lines a minute — 7.3 MB of one identical failure was observed on an instance whose key
  needed an agent.

### Changed

- **The backend log is bounded.** Past `backend.log_max_bytes` (16 MiB) it rotates, keeping
  `backend.log_generations` (3) as `backend.log.1` … `.3` — at most 64 MiB, where before it reached
  **62 MB over 491,225 lines** and had to be truncated by hand. Only a backend whose own stdout *is*
  the log rotates it, so a foreground run on a terminal keeps its console.
- **A request is logged once, not twice.** uvicorn's access line was the third line per request and
  carried the least — no duration — so it is off. The register that measures which operations the
  running application has executed reads both formats now, because its history is all in the old one.
- **`tests/architecture/` runs in 42 s again, not over ten minutes.** The retired-route scan was
  reading 841 MB of istanbul coverage output that had appeared in `tools/gui/.nyc_output`.

### Model

- **`FMD@1785065977`'s occurrence judgement is re-recorded with the right date** — its rationale put
  the analysis baseline at 2026-08-26 where the baseline is 2026-07-26. Value unchanged at `unlikely`,
  same basis digest, revision 1 retained; the prior text's unreproducible commit count is dropped
  rather than repeated.

## [0.5.1] — 2026-08-11

**[Full detail → `changelog-assets/0.5.1-detail.md`](changelog-assets/0.5.1-detail.md)**

Nothing here changes an API, a contract, or observable behaviour.

### Fixed

- **A malformed `local:` in `arch-workspace.yaml` is refused by name instead of crashing.** A bare
  `local:` key, a list or a mapping raised an unhandled `TypeError` at startup; it now reports
  `ERROR: <label>.local must be a non-empty string`, as every other mistake in that file already did.
  An empty string is refused too — `Path("")` resolves to the workspace root.
- **`assurance_list_vulnerabilities` reports one `assessed_entity_id` per entity.** The entity-scoped
  read echoed the caller's argument while the unscoped read reported the stored canonical id, so
  joining the two result sets on that field matched nothing. Both now report the stored id.
- **A killed render no longer leaves a `tmp*.puml` in the diagram catalog.** Cleanup ran in a `finally`,
  which a SIGKILL or OOM kill skips; each render now discards scratch files older than 300 s first.

### Changed

- **One loader parses all YAML** (`domain.yaml_documents.parse_yaml`), using `libyaml` where the
  install has it and falling back to the pure-Python loader where it does not. 77 call sites chose the
  slow loader independently. Measured: 9.5× on this repository's YAML corpus, 2.73× on a full
  verification pass (516 ms → 189 ms); 0 of 1,514 stored documents parse differently.
- **One definition of the frontmatter block** (`domain.repository.frontmatter`), replacing fourteen that
  disagreed — the verifier and the document write path held the two loosest, so a file could be
  verified under one delimitation and rewritten under another. The surviving reading is the most
  tolerant of the fourteen: CRLF, trailing whitespace on either fence, and a closing fence that may end
  the file. Measured: across 975 files the old readings disagree on zero, and all agree with the new one.
- `_DEFAULT_PASS_WORKERS` stays 1, for a re-measured reason. The 63 s pass its justification cited is
  now 0.19 s: single acquisition removed the re-reading (200,574 YAML documents → 1,472; 982,904
  `realpath` calls → 3,392), so there is no pass left to divide.
- **Coverage measures what it gates.** `.vue` files leave the unit-coverage population — v8 measures a
  component's compiled render function while the E2E flag measures its source through istanbul, and the
  two disagree about line numbers. Frontend coverage reads 53.0% → 68.3% once they stop double-counting,
  and `src/ui/components` and `src/ui/views` turn out to be at 95.8% and 92.1% rather than 18.7%. Every
  frontend directory now carries a floor, and the backend ratchet moves 74 → 85.
- `tools/gui/package-lock.json` records the current version; it had read `0.3.0` since that release.

## [0.5.0] — 2026-08-10

**[Full detail → `changelog-assets/0.5.0-detail.md`](changelog-assets/0.5.0-detail.md)**

Supersedes 0.4.0. No GitHub release exists for 0.4.0 and none should.

### Changed

- **BREAKING — `artifact_submit_for_review` takes `dry_run`, defaulting to `true`.** The bare call now
  reports the branch it would push and pushes nothing. **Pass `dry_run=false` to submit.**
- **Deselecting a diagram entity: clicking the same entity no longer clears the selection.** Click away
  from any entity, connection or sub-part to clear. Applies to every diagram view. Panning unaffected.
- `destination` is imported from the domain by every contract that declares it. The file reader heals
  an unrecognised value to `undecided`; the request boundaries reject one, against the caller's own
  rows only.

### Added

- Fullscreen diagram views keep their sidebar: it moves inside the fullscreen element and animates in
  on selection, out on deselection. Honours `prefers-reduced-motion`. Entering fullscreen no longer
  remounts it.
- `analysis_id` on `assurance_stats`, `assurance_coverage`, `assurance_risk_register`,
  `assurance_stpa_complete`, `assurance_cast_complete` and `assurance_grc_complete`. Omit it for the
  whole store. Scoping is by node; edges follow their endpoints.
- Typed request contracts for the scratchpad delta body, the whole-document body, and the MCP write
  tools' parameters.

### Fixed

- A scratchpad holding an unrecognised `destination` is readable again.
- Four diagram types were not exercised in CI; their suite is no longer parametrized over
  environment capabilities.
- `assurance_scan_ai_candidates` now reads `artifact_id` / `artifact_type` / `summary` as well as
  `entity_id` / `entity_type` / `description`, so arch-repo-read output yields identified candidates.
- A `src/domain/**` coverage floor and an IPv4/IPv6 bind mismatch.

### Notes for maintainers

- MCP tool returns remain `dict[str, object]` with an open `outputSchema`.
- Four tools take no parameters by design, recorded in a two-way register: `assurance_store_status`,
  `artifact_help`, `assurance_security_stats`, `assurance_verify`.
- MCP tools named literally in tests: 69 → 86.

## [0.4.0] — 2026-08-10

**[Full detail → `changelog-assets/0.4.0-detail.md`](changelog-assets/0.4.0-detail.md)**

**Somewhere to think before anything is typed.** The typed model asks a contributor to name an
element type before they have decided anything, and that question is the wall this removes.

### Added

- **A scratchpad tier.** Notes and links on one canvas with four labelled frames, no ontology
  involved: a note needs only a title, and which frame it is in is where it sits. The canvas saves
  at most once a second after editing settles, so the endpoint sees a save and never a drag.
- **Refinement, one level at a time**, down the meta-ontology's own classification levels — which
  `classification_levels` now lets a module declare rather than every consumer hard-code. Or bind a
  note to an element the model already has, and it takes that element's type.
- **A link carries its verdict.** A refusal at the level relationships are keyed on (**E126**) blocks
  a lift; a specialization narrowing (**W128**/**W129**) warns. A refusal leads with *Reverse the
  link* when the reverse is the permitted one.
- **Lift, preflighted.** A selection becomes ordinary verified model content through the same write
  path as any other authoring, into a model-project chosen **per frame**. The dialog says what would
  be created, what is refused and why, what is already in the model, and which links reach outside
  the selection; a refusal blocks the whole lift, because the write is one transaction. A lift never
  writes back, so a second one creates only what is new. Documents are a destination too, and a lift
  can draw a view of what it made.
- **Nothing is permanent until it is lifted.** A note, a link or any refinement can be taken back on
  every surface. Removal never retracts model content: deleting a realized note leaves the entity.
- **`PATCH /api/scratchpads/{id}` and `scratchpad_edit` change a scratchpad by delta** — the same
  write as `PUT`, at a payload proportional to the edit rather than to the canvas. A patch is a merge
  patch: a key left out keeps its stored value, `null` clears it, an unknown id creates the row.
- **Scratchpad notes are searchable**, and rank below model content, documents and diagrams — a note
  is a half-formed thought and an entity is a commitment. A hit opens the canvas it sits on.
- **Focus mode**, and a canvas operable without a pointer: the notes layer is a real multi-select
  listbox, every gesture has a key, and what is selected is announced rather than only drawn.
- **Seven MCP tools and seven REST operations, held equal by a parity test.** The scratchpad is the
  lowest-barrier surface, so a human-only version would make the one place newcomers start the one
  place an agent cannot help.
- **A diagram can fill the screen**, from a control beside Reset, and Esc gives the page back. The
  view is re-framed against the space it gains and the space it loses.

### Fixed

- **A diagram can be dragged by the boxes on it.** Panning was declined outright wherever the press
  landed on something selectable, so a dense view could only be moved by its auto-created grouping
  boxes. Travel now separates the two gestures: a press that stays put selects, a press that moves
  pans and does not also select what it started on.
- **A C4 element is selectable again, and its drill-down badges are back.** The write path strips
  `entity_id` from every item because the `bindings` block is what disk holds; nothing put it back
  for the three readers that need it, and every test built its fixtures with the shorthand present
  — describing a shape no persisted diagram has ever had.
- **A render that fails is reported as a failure.** A PlantUML crash was returned as
  `valid: true` with the stack trace filed under warnings; it is now an **E350** error. The hidden
  ordering chains that caused the crash are dropped above 24 boxed members, and `puml="auto-sync"`
  refuses an edit that carries anything else rather than silently discarding it.
- **A network stall stops being reported after the network returns.** A failed fetch was cleared
  only by a poll that reached a fully grounded state, so one timeout stayed visible across every
  later healthy poll.
- **An ArchiMate box is no longer as wide as its widest unwrapped label.** All seven `archimate-*`
  types emitted no `skinparam wrapWidth`; on one diagram 2545×798 became 1671×952. All 32 committed
  diagrams were re-rendered and every one still lays out.
- **Every diagram-owned type now says how to author one.** Guidance described the schema of
  `diagram_entities` and said nothing about the authoring protocol, which had to be
  reverse-engineered from an existing `.puml` — silently, since the diagram still rendered.

## [0.3.1] — 2026-08-08

**[Full detail → `changelog-assets/0.3.1-detail.md`](changelog-assets/0.3.1-detail.md)**

**Nothing the product serves changed shape.** A cold verification no longer takes the backend with it.

### Fixed

- **A whole-repository verify no longer blocks every other request for its duration.** It held the
  workspace gate for the whole pass and ran on the event loop; it now reads under exclusivity (192 ms
  for 880 files) and evaluates outside it. Identity p95 during a pass went from 5.9x idle to 1.5x.
- **Verification could deadlock a promote or a cascade-delete**, which verify while holding the
  non-reentrant write gate. A full pass reached from the incremental path also swept the tree twice,
  recording files as verified at contents they never held. A waiting writer was unreachable under
  sustained reads, and lock ownership was mirrored in a thread-local that offloading invalidates.
- **A second backend on one machine served its MCP tools from the *first* workspace's repository**,
  while reporting its own roots on `/api/backend-identity`: the MCP layer resolved its default
  repository from where the code lives, not from what the backend serves, so reads, writes and
  deletes could land in a neighbour's model. Only multi-workspace deployments were affected.
- **A diagram no longer draws a domain box for a domain an authored grouping emptied**, which a
  grouping spanning several domains leaves behind for each domain it draws from.

### Changed

- **`artifact_verify` refuses an unconfirmed full pass** in milliseconds, naming which of four
  conditions requires it and how many files it would read; pass `confirm_full_pass=true` or set
  `ARCH_MODEL_VERIFY_MODE=full`. A concurrent pass is refused, not queued; a cancelled one leaves no
  state. It **verifies one file at a time now** — the pool cost 4x the wall clock and 4.4x the CPU
  for the same files; `ARCH_VERIFY_WORKERS` opts back in.

## [0.3.0] — 2026-08-08

**[Full detail → `changelog-assets/0.3.0-detail.md`](changelog-assets/0.3.0-detail.md)**

Several workspaces can now run on one machine without reaching into each other. An entity can be
drawn more than once on a diagram and connected differently in each place. And `arch-repair upgrade`
repairs references that name an artifact by a name it no longer has.

### Added

- **A diagram can draw an entity more than once and connect each drawing differently.** Each drawing
  gets its own row in Included Entities, with its own connections and its own related-entity list. A
  relation may be drawn once per pair of drawings, so a cluster duplicated to keep arrows untangled
  reads as a complete unit in each copy. Existing diagrams are unaffected.
- **Diagrams can draw labelled boxes the model does not hold, and the boxes style themselves.**
  `authored_groupings` reaches `artifact_create_diagram`, `artifact_edit_diagram`, the REST write
  routes and a Groupings panel in the GUI; the key rendered before but was reachable only by
  hand-editing the file. The look is derived from the members. A member may name an occurrence id, so
  an entity drawn twice sits in a different box each time, and boxes nest.
- **`arch-repair upgrade` respells references that name an artifact by a former slug** — in
  repository files and in the confidential store's architecture references. Dry-run by default,
  `--commit` to apply; both steps decline where a stem has two current spellings rather than guessing.
- `--workspace` / `ARCH_MCP_WORKSPACE` for the MCP bridges, for clients that cannot set a working
  directory. A bridge with no backend of its own exits with the reason instead of attaching to one
  that is not its.
- **A goal realized through the goals it aggregates is no longer a gap.** `motivation-coverage` now
  declares the whole-part edge it composes over (`rollup`), so an aggregate carries its constituents'
  obligations instead of one of its own, at every level.
- **`assurance_guidance` teaches the five UCA guidewords the software applies**, and says why the
  Handbook's second is split in two. New topic `stpa-loss-scenarios` covers the step that had no
  guidance at all. Every STPA answer states how its six step numbers map onto the Handbook's four.

### Fixed

- **`arch-backend --daemon --port` could fail to start**, because the daemon matched its own launcher
  as an instance already serving that port. Startup now waits for the process to begin serving rather
  than for a fixed number of seconds, so a large repository's first index build no longer times out.
- **A preview now shows the diagram the write will save.** Authored groupings reached both writes and
  never the preview, and the two rendered different input, so a box was invisible until saved.
- **Six further fixes**, each with its own section in the detail file: connection ids minted from a
  hyphen-free alphabet, so a composite id no longer splits in the wrong place; AND/OR junctions no
  longer a dead end for tracing (`RJ3`); a junction refused a relationship its participants could not
  hold (**E128**/**E129**); a diagram naming an artifact by a former slug reported
  (**W305**/**W306**); a batched rename rewriting its referring files, as a single-entity rename
  always did; and `entity_ids` on `artifact_edit_diagram` setting what the diagram draws, as it
  always has on create.
- **A rename now reaches the confidential assurance store, when it is unlocked.** A registered
  follower retargets the stored references, matching on the stem so an older spelling heals too. A
  locked or unconfigured store means no failure.
- **A batch item carrying a field its operation does not accept is refused, not performed
  differently.** An item passing `mode: "remove"` had that field ignored, ran as an update, and
  reported `wrote: true` for a removal that never happened. Every op declares its accepted fields.
- **"Browse" no longer carries a diagram type into the entity browser as a filter.** Arriving from a
  diagram page set the entity-type filter to a value no entity matches, showing an empty list.
- **A grouping's realization now reaches its members, as a visible inference** carrying
  `diagnostic_code: potential_realization` — a relationship of a whole only potentially holds of each
  part (`PDR12`). An empty grouping still realizes nothing.
- **A client reaches the backend serving its own workspace, or none.** Endpoints are chosen by what a
  backend reports serving (`GET /api/backend-identity`), not by which port answers.
- **`arch-write-cli` refuses to write** to a backend that does not serve the `--repo-root` it was
  given, rather than trusting a recorded port another instance may have taken over.
- **`arch-assurance unlock` authorizes only this workspace's backend.** Addressed by port, it could
  reach a neighbour's — one workspace's unlock ceremony granting access to another's store.
- The GUI dev proxy and the browser suite follow `ARCH_BACKEND_PORT`, so developing against a second
  workspace no longer renders the first one's model.

### Security

- **Five advisories closed before release** — `cryptography` to 50.0.0, `nanoid` to 3.3.18,
  `dompurify` to 3.4.13, and `js-yaml` to 3.15.1 and 4.3.1. Two arrived as dependency PRs; the
  other three are transitive and had none, so `js-yaml` needed an override scoped to
  `@redocly/openapi-core` rather than a global pin, which would have broken `nyc`'s 3.x
  requirement. Both audit surfaces report clean, and the product's own supply-chain ingest was
  re-run against live OSV data for the backend and the GUI — 114 and 384 components, no findings.

### Breaking — what you must change

- **`artifact_bulk_write` answers with one object for the batch, not a list of items.** Read
  `payload["items"]` where you read the list. New `return_mode` defaults to `'summary'` (only items
  with a warning or error); pass `return_mode='full'` to keep the previous per-item detail. The batch
  states `operation_id`, `counts`, `item_count`, `failed_count`, `committed` and `refs` once instead
  of repeating them per item, so correlating an alias to its id no longer depends on input order.

## [0.2.1] — 2026-08-04

**[Full detail → `changelog-assets/0.2.1-detail.md`](changelog-assets/0.2.1-detail.md)**

**Nothing the product serves has changed** — no API, no payload, no behaviour. `0.2.0` was tagged
against a CI run that then went red; this release carries the fixes and closes the gap that let it
happen.

### Fixed

- Three defects in tests and build configuration: a frontend coverage floor that was no longer
  enforced, a dev-proxy test that bound one address and connected to another, and an index-close test
  failed by connections other tests had leaked.

### Quality

- `AGENTS.md` now names every gate CI runs, and a fitness function fails when `ci.yml` gains one it
  does not. Nine were missing — including `npm run test:coverage`, which is the only command that
  applies the frontend coverage thresholds.

## [0.2.0] — 2026-08-03

**[Full detail → `changelog-assets/0.2.0-detail.md`](changelog-assets/0.2.0-detail.md)** ·
**[Route map → `changelog-assets/0.2.0-route-map.md`](changelog-assets/0.2.0-route-map.md)**

The release makes the REST surface something you can generate a client against and trust: every
response body is a declared, closed contract, every operation is addressed by one canonical path, and
one error vocabulary covers REST and MCP alike. That consolidation is what the breaking changes buy —
**there are no aliases and no redirects**, so every consumer moves once, here. Persisted local data is
migrated non-destructively; nothing else is.

### Added — typed bodies and a navigable contract

- **Every response body is a closed, declared model.** No operation publishes an untyped body any
  more: the 69 that answered `additionalProperties: true` behind a shared placeholder are gone, and
  the ledger that tracked them is empty. A body the contract does not describe now fails on the server
  rather than reaching a client that was promised otherwise. The open maps that remain are *named*
  fields whose keys are repository or module data — `attributes`, `properties`, `extra`,
  `display_blocks`, `metadata` — each rostered with its reason.
- **The OpenAPI document is an oracle you can build against.** It is generated from those models, and
  the frontend's own decoders are held against it every commit, so a generated client and the server
  cannot drift apart silently. `operationId` is stable across this release's renames, so a client keyed
  by operation id needs only the new paths.
- **`/docs` is navigable.** Every one of the 166 operations carries exactly one tag — 59 had none, so a
  third of the surface sat under "default" — and the assurance surface subdivides into six sections.
  `/docs/architecture` and `/docs/assurance` render the same document filtered, with
  `/openapi/{section}.json` beside them. The contract itself is not split: one document, one client.
- **Every response carries `X-Request-ID`**, echoed from the request when supplied; every error
  response carries `Cache-Control: no-store`.
- **The document's version is the package version.** It read `0.3.0` against a `0.1.0` package, so a
  client pinning the document version was pinning a number nothing produced.

### Breaking — what you must change

- **79 routes are renamed.** `operationId` is unchanged across the renames, so a generated client keyed
  by operation id needs only the new paths. The route map lists every one with its replacement.
- **Every error body changes shape.** `detail` is an object, not a sentence:
  `{"detail": {"code", "message", "details", "request_id"}}`, with `code` a closed vocabulary.
  **Anything parsing `detail` as a string must change** — including on the assurance surface, which had
  an error vocabulary of its own, so a client branching on `detail.code` fell through on every refusal
  it made.
- **Partial updates are `PATCH`, whole-resource replacements are `PUT`; `POST …/edit` is gone.**
  Deletions return `204` with no body — except a dry run, which returns `200` with its envelope.
- **Four operations split or collapsed** and so cannot appear as renames: `GET /api/ontology` became
  `…/classification` and `…/pairs`; the four `*-complete` endpoints became one method-discriminated
  `…/completeness`; `POST /api/assurance/security-snapshot-delete` became two addresses; the unscoped
  FMEA matrix is gone.
- **An assurance node is created inside its provenance analysis**, and provenance is mandatory.
  Participation is an idempotent relation on `…/participating-nodes/{node_id}`, not a collection post.
- **A concept's specializations are one field.** The scalar `specialization` is gone from every response
  and every write input; `specializations` is the ordered set (ArchiMate §15.2 permits several). Send
  `["x"]` where you sent `"x"`, `[]` to clear; read `specializations[0]` where you read the scalar. The
  on-disk frontmatter key keeps its singular name and its scalar-or-list value, so **no repository
  migration is needed**, and the `?specialization=` selector on `GET /api/entity-schemata/{type}` is a
  different thing and unchanged.
- **`assurance_create_node` requires `analysis_id`**, and MCP execution errors now report the REST
  error vocabulary — one word per failure across both surfaces.
- **`dry_run` defaults to `true` on every write.** The three document routes and
  `DELETE /api/viewpoints/{slug}` defaulted to committing; they now plan. Pass `dry_run: false` (body)
  or `?dry_run=false` (query) to commit, as the other 25 operations always required.
- **Document writes answer 404 for an absent artifact and 400 for a malformed payload**, not 500.
- **`POST /api/identifiers/allocate` no longer accepts `owner_kind`.** It was in the schema, hard-coded
  by every caller, and read by nothing. `diagram_type` and `entity_type` remain required.
- **A rejected viewpoint parameter's `message` no longer carries a retired code word.** Branch on
  `detail.code` and read the parameter from `details.field_errors[].field` (`path` on MCP).
- **`arch-gui-server` is gone.** It raised `ModuleNotFoundError` on any invocation; use `arch-backend`.

### Fixed

Eleven defects, every one reachable in ordinary use and invisible to the gates that existed when it
shipped; all eleven are listed in the detail file. The two that affect deployments rather than the
UI: **security-signal ingest refused every anchor unless the server ran from its workspace
directory** (any deployment configuring `ARCH_REPO_ROOT` without a workspace config — a mode the
shipped container supports), and **a domain card on the Home page opened the last-browsed project**
rather than the repository-wide list its count was computed over.

### Quality

Every REST operation and every MCP write tool is now exercised over its own transport, against a
disposable repository and a disposable confidential store, and the register that tracked
never-requested operations is empty — the reason to trust a release which renames 79 routes.

## [0.1.0] — 2026-07-29 — first public release
- Typed, git-versioned architecture repository (ArchiMate 4) with GUI, REST, and MCP surfaces
- Two-tier engagement/enterprise model with reviewed promotion (plan-time closure, git-transactional rollback)
- Generated diagram catalog with authored-grouping preservation and manual-layout protection
- Confidential assurance tier (STPA/CAST/GRC/FMEA/GSN) on an encrypted store with tamper-evident history
- Viewpoint query engine with diagram/matrix/table representations

[0.7.1]: https://github.com/mbauer83/architectonic/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/mbauer83/architectonic/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/mbauer83/architectonic/compare/v0.5.4...v0.6.0
[0.5.4]: https://github.com/mbauer83/architectonic/compare/v0.5.3...v0.5.4
[0.5.3]: https://github.com/mbauer83/architectonic/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/mbauer83/architectonic/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/mbauer83/architectonic/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/mbauer83/architectonic/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/mbauer83/architectonic/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/mbauer83/architectonic/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/mbauer83/architectonic/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/mbauer83/architectonic/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/mbauer83/architectonic/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mbauer83/architectonic/releases/tag/v0.1.0
