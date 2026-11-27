"""MCP edit tool description text."""

#: Said once for the two tools that take groupings, so create and edit cannot describe them apart.
GROUPING_RULES_AND_IDS = (
    "Instead of entity-ids a grouping may state rule: {domain: <name>} or rule: {type: <element type>} "
    "(within its parent) and then holds whatever of the diagram the rule admits; a listed grouping "
    "claims its members first, then the most specific rule. Once any grouping is ruled, the stated "
    "groupings are the diagram's whole list of boxes: no domain or type box is computed, and what no "
    "grouping holds stands unboxed. Every grouping has a stable id ('g-…'): send back the id you read "
    "to keep a box's identity; one sent without an id is new and is given one."
)

#: Said once for the two tools that take a whole layout block.
LAYOUT_ARGUMENT = (
    "layout: the diagram's whole layout block — geometry only, for a diagram drawn from the model: "
    "{grid, elements: {<instance id>: {x, y, w?, h?}}, boxes: {<grouping id> | 'rule:domain=<name>' | "
    "'rule:domain=<name>/type=<element type>': {x, y, w?, h?}}, relations: {<relation key, as for "
    "edge_labels>: {from: {side, at}, to: {side, at}, via: [[x, y], …], label: {at, dx, dy}}}, "
    "z: {<instance or box>: <int>}}. Positions and sizes are whole numbers, side is top|right|bottom|"
    "left, at is a fraction 0–1. Every key must name something the diagram holds. Pass {} to remove "
    "the layout and return the diagram to PlantUML's arrangement with nothing else changed; omit to "
    "keep it. A diagram is either manual-layout or laid out, never both. This stores and verifies a "
    "layout; the stored picture is still PlantUML's."
)

#: Said once for the two tools that take a diagram's purpose line, so create and edit cannot describe it apart.
PURPOSE_LINES_ARGUMENT = (
    "stakeholders / concerns: who the diagram is for and what it answers. Each is a list whose entries "
    "are prose ('Operations team') or a reference {ref: <artifact id>} — a stakeholder element for "
    "stakeholders, a motivation element (driver, goal, assessment, requirement, …) stating the concern "
    "for concerns. A reference to a missing element is refused (E186), to an unsuitable type too "
    "(E187). A diagram applying a viewpoint shows the viewpoint's lists wherever it states none of its "
    "own. On edit, omit a list to keep it and pass [] to clear it."
)

EDIT_ENTITY_DESCRIPTION = (
    "Edit an existing entity. Pass only fields to change; omitted fields are preserved. "
    "Supports name, summary, properties, notes, keywords, version, status, "
    "group (str|None — re-home to a different model-project slug). "
    "properties and attribute_types are PATCHED key by key: send only the attributes you are "
    "changing and the rest are kept. Map a key to null to remove that attribute. "
    "accepted_advice acknowledges advice findings (artifact_verify's 'advice'), as [{code, reason}] "
    "with a short reason; it replaces the stored set and [] clears it. An acknowledged advice is quiet "
    "at every status. Only advice codes (A…) are accepted — a warning or error code is refused. "
    "Bumps last-updated automatically. Regenerates macros if name changes. "
    "artifact_id: full (PREFIX@epoch.random.slug) or short (PREFIX@epoch.random) form."
)

EDIT_CONNECTION_DESCRIPTION = (
    "Edit or remove a connection in an .outgoing.md file. "
    "Identify by source_entity + target_entity + connection_type. "
    "operation='update' (default) changes description, src_multiplicity, tgt_multiplicity, "
    "specialization(s), and/or metadata; pass '' to remove an existing multiplicity or "
    "specialization, omit (null) to preserve. metadata is PATCHED key by key like entity "
    "properties: send only the keys you change; map a key to null to remove it. "
    "operation='remove' deletes the connection. "
    "source_entity/target_entity: full (PREFIX@epoch.random.slug) or short (PREFIX@epoch.random) form."
)

EDIT_CONNECTION_ASSOCIATIONS_DESCRIPTION = (
    "Add or remove second-order association entity IDs from a connection. "
    "Associations link a connection to additional entities beyond source and target "
    "(stored as <!-- §assoc ENTITY_ID --> annotations). "
    "add_entities and remove_entities may both be provided in one call. "
    "source_entity/target_entity: full (PREFIX@epoch.random.slug) or short (PREFIX@epoch.random) form."
)

EDIT_DIAGRAM_DESCRIPTION = (
    "Edit an existing diagram. "
    "Binding modes (pass mode=): 'refresh-derivation'"
    " (requires derivation_id — runs strategy, returns diff + base_revision, no write); "
    "'apply-diff' (requires diff + base_revision — applies diff with stale-write check); "
    "'propose-bindings' (requires entity_ids/connection_ids — returns proposals, no write); "
    "'detach-binding' (requires binding_id — removes binding). "
    "Default (no mode): puml='auto-sync' is projection-aware — scope-bound diagrams "
    "re-run their projector (never deleted on empty result); ArchiMate diagrams reconcile "
    "refs; standalone diagrams re-render. Explicit puml replaces the body and may be compact — "
    "the standard header (skinparams, Rel_ defines, stereotype sprites) is auto-injected. "
    "entity_ids/connection_ids without puml SET what the diagram draws: exactly those entities, "
    "with the body regenerated to match — so dropping an id removes that element, and any "
    "connection that loses an endpoint. Omit connection_ids to draw whatever the model connects "
    "the members with. To supply the body yourself instead, pass puml together with entity_ids: "
    "your body is kept and the recorded refs are reconciled against it. "
    "WITH puml, entity_ids and connection_ids each REPLACE the recorded list — passing them is "
    "stating the set, so this is how you correct a diagram whose refs are wrong (e.g. a view re-cut "
    "to a narrower scope). Omit them and the refs are inferred from the body instead, which is "
    "deliberately conservative: a stored ref is dropped only where the body positively contradicts "
    "it, and a hand-laid ArchiMate body draws plain arrows that cannot be attributed, so nothing is "
    "contradicted and nothing is dropped. `artifact_verify` names each wrong entry (W307). "
    "entity_ids/connection_ids are ALSO honoured beside puml='auto-sync', and only there do they "
    "leave the body untouched — which is how a hand-laid diagram's lists are corrected without "
    "resending its layout. A sync that would regenerate the body refuses them, because that body "
    "decides its own references. Three kinds of diagram "
    "own their picture another way and refuse entity_ids, naming what to use: model-backed "
    "(change its scoped-by binding, then puml='auto-sync'), standalone (pass diagram_entities), "
    "manual-layout (pass puml in the same call, or manual_layout=false). "
    "authored_groupings behaves the same way and replaces the diagram's boxes wholesale: "
    "[{label, entity-ids: [...], groups: [ ...nested... ]}]. A member may name an entity id or an "
    "occurrence id, so an entity drawn twice can sit in a different box each time; each drawing "
    "belongs to one box, first declaration winning. The look is DERIVED — members all in one domain "
    "give that domain's look, members from several give the dashed ArchiMate grouping look — so omit "
    "stereotype unless you mean to override it. " + GROUPING_RULES_AND_IDS + " " + LAYOUT_ARGUMENT + " "
    "Frontmatter fields updated if provided; bindings merges + normalizes shorthand. "
    "ArchiMate occurrence edits may pass diagram_entities={'occurrence': "
    "[{'id': '<occurrence-id>', 'backing_entity_id': '<model-entity-id>'}]}; "
    "the occurrence id distinguishes the diagram element and visual_role is optional metadata. "
    "edge_labels: per-diagram edge-label overrides, merged into the stored ones — each keyed by the "
    "relation it labels: the connection's artifact_id, or '<connection id>@<source instance>><target "
    "instance>' where an end is a further occurrence (an instance is an entity id or an occurrence "
    "id); a connection the diagram holds itself is keyed by its id within the diagram. A null value "
    "removes that key; omit to keep the stored overrides. "
    "viewpoint: replace the diagram's ViewpointApplication frontmatter — "
    "{slug, version, enforcement_override?, derivation_params?}; omit to keep the existing "
    "application (if any) unchanged. Call artifact_query_viewpoint(action='list') to discover "
    "slugs/versions; a viewpoint applied to a diagram type it does not list in representation_types "
    "is allowed and reported as W183. " + PURPOSE_LINES_ARGUMENT + " "
    "group (str|None — re-home to a different diagram-collection slug; moves the source "
    "file and its rendered PNG/SVG; only applies to the default write path, not mode= "
    "dispatch or puml='auto-sync'). "
    "Re-verifies and re-renders PNG on every write. "
    "Matrix diagrams (diagram-type: matrix) are markdown tables, not PUML: only "
    "name/keywords/version/status/tlp/group are supported here (metadata + group move, "
    "table content preserved); puml/diagram_entities/diagram_connections/bindings/viewpoint/"
    "stakeholders/concerns/etc. "
    "are rejected — call artifact_create_matrix with artifact_id set to change table content. "
    "artifact_id: full (PREFIX@epoch.random.slug) or short (PREFIX@epoch.random) form."
)

DELETE_ENTITY_DESCRIPTION = (
    "Delete a single entity (and its own .outgoing.md file, if any). Blocks with a dependency "
    "list if the entity has incoming connections, is referenced by any diagram, or has a global "
    "entity reference — delete or update those first. For a batch, or when dependents should be "
    "deleted/reconciled together in one transaction, use artifact_bulk_delete instead; this tool "
    "is the lighter-weight single-item path (no full-repo staging copy). "
    "artifact_id: full (PREFIX@epoch.random.slug) or short (PREFIX@epoch.random) form."
)

DELETE_DIAGRAM_DESCRIPTION = (
    "Delete a single diagram, including its rendered PNG/SVG output. Blocks if any classifier the "
    "diagram hosts is still referenced by another diagram. For a batch, or a cascade spanning "
    "connections/entities/diagrams together, use artifact_bulk_delete instead; this tool is the "
    "lighter-weight single-item path (no full-repo staging copy). "
    "artifact_id: full (PREFIX@epoch.random.slug) or short (PREFIX@epoch.random) form."
)
