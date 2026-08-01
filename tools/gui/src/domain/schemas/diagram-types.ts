import { Schema } from 'effect'

export const DiagramSummarySchema = Schema.Struct({
  artifact_id: Schema.String,
  name: Schema.String,
  diagram_type: Schema.String,
  version: Schema.String,
  status: Schema.String,
  path: Schema.String,
  group: Schema.optional(Schema.String),
  is_global: Schema.Boolean,
  last_updated: Schema.optional(Schema.NullOr(Schema.String)),
})
export type DiagramSummary = typeof DiagramSummarySchema.Type

export const DiagramListSchema = Schema.Struct({
  total: Schema.Number,
  items: Schema.Array(DiagramSummarySchema),
})
export type DiagramList = typeof DiagramListSchema.Type

export const DiagramTypeSummarySchema = Schema.Struct({
  key: Schema.String,
  label: Schema.String,
  description: Schema.String,
})
export type DiagramTypeSummary = typeof DiagramTypeSummarySchema.Type

/** `entity_type` and `entity_class` are always sent and null where the source names the other kind —
 *  they were `optional` here, so "maps from a class, not a type" read as "field absent". */
export const MappingSourceSpecSchema = Schema.Struct({
  ontology: Schema.String,
  entity_type: Schema.NullOr(Schema.String),
  entity_class: Schema.NullOr(Schema.String),
  transparent: Schema.Boolean,
})
export type MappingSourceSpec = typeof MappingSourceSpecSchema.Type

export const PermittedMappingSpecSchema = Schema.Struct({
  entity_types: Schema.Array(Schema.String),
  entity_classes: Schema.Array(Schema.String),
  sources: Schema.Array(MappingSourceSpecSchema),
})
export type PermittedMappingSpec = typeof PermittedMappingSpecSchema.Type

export const DiagramOwnEntityTypePropertySpecSchema = Schema.Struct({
  name: Schema.String,
  // A JSON Schema fragment: its keywords are that specification's, not this surface's.
  schema: Schema.Record({ key: Schema.String, value: Schema.Unknown }),
  required: Schema.Boolean,
})
export type DiagramOwnEntityTypePropertySpec = typeof DiagramOwnEntityTypePropertySpecSchema.Type

/** One editable descriptive-metadata field of a diagram-only entity type, with the input widget
 * an editor should render for it. The single source is the diagram type's config — never hardcoded
 * field lists in the panels. */
export const EditableMetadataFieldSchema = Schema.Struct({
  field: Schema.String,
  control: Schema.String,
})
export type EditableMetadataField = typeof EditableMetadataFieldSchema.Type

export const EditableMetadataSpecSchema = Schema.Struct({
  entity: Schema.Array(EditableMetadataFieldSchema),
  subparts: Schema.Record({ key: Schema.String, value: Schema.Array(EditableMetadataFieldSchema) }),
})
export type EditableMetadataSpec = typeof EditableMetadataSpecSchema.Type

export const PermittedRelationshipSchema = Schema.Struct({
  source_type: Schema.String,
  target_type: Schema.String,
  connection_type: Schema.String,
})

/** `cardinality_max` null means unbounded. */
export const RequiredConnectionSchema = Schema.Struct({
  connection_type: Schema.String,
  target: Schema.String,
  cardinality_min: Schema.Number,
  cardinality_max: Schema.NullOr(Schema.Number),
})

/**
 * One construct a diagram type owns rather than borrowing from the model.
 *
 * This schema described ten of the eighteen fields the route sends, and declared two of those ten
 * optional though it always sends them. The eight it omitted are the ones that govern authoring:
 * `identity_scope` decides whether editing one diagram can affect another, and
 * `permitted_connections` is what a construct may legally connect to — invisible to a client that had
 * decoded the config successfully.
 *
 * `permitted_connections` used to arrive as `{"_rules": [...]}`, the private field of a domain
 * dataclass serialised by `asdict`. It is a list of triples now, projected through the set's public
 * reading.
 */
export const DiagramOwnEntityTypeUiConfigSchema = Schema.Struct({
  entity_type: Schema.String,
  label: Schema.String,
  plural: Schema.String,
  min: Schema.Number,
  max: Schema.NullOr(Schema.Number),
  permitted_mappings: PermittedMappingSpecSchema,
  mapping_required: Schema.Boolean,
  classes: Schema.Array(Schema.String),
  create_when: Schema.String,
  never_create_when: Schema.String,
  properties: Schema.Array(DiagramOwnEntityTypePropertySpecSchema),
  permitted_connections: Schema.Array(PermittedRelationshipSchema),
  required_connections: Schema.Array(RequiredConnectionSchema),
  // Null where nothing is managed, as against an empty list meaning "managed, nothing yet".
  managed_fields: Schema.NullOr(Schema.Array(Schema.Array(Schema.String))),
  identity_scope: Schema.Literal('diagram', 'workspace'),
  id_prefix: Schema.NullOr(Schema.String),
  include_in_global_search: Schema.Boolean,
  editable_metadata: EditableMetadataSpecSchema,
})
export type DiagramOwnEntityTypeUiConfig = typeof DiagramOwnEntityTypeUiConfigSchema.Type

export const DiagramTypeUiConfigSchema = Schema.Struct({
  label: Schema.String,
  description: Schema.String,
  entity_search_filter: Schema.Boolean,
  diagram_only_types: Schema.Array(DiagramOwnEntityTypeUiConfigSchema),
  type_ui_slots: Schema.Record({ key: Schema.String, value: Schema.String }),
  primitive_types: Schema.Array(Schema.String),
})
export type DiagramTypeUiConfig = typeof DiagramTypeUiConfigSchema.Type

export const DatatypeClassifierInfoSchema = Schema.Struct({
  type_id: Schema.String,
  label: Schema.String,
  kind: Schema.String,
  scope: Schema.String,
  host_diagram_id: Schema.String,
})

export const DatatypeTypeCatalogSchema = Schema.Struct({
  generation: Schema.Number,
  primitives: Schema.Array(Schema.String),
  classifiers: Schema.Array(DatatypeClassifierInfoSchema),
  next_cursor: Schema.NullOr(Schema.String),
})
export type DatatypeTypeCatalog = typeof DatatypeTypeCatalogSchema.Type

export const DatatypeTypeUsageSchema = Schema.Struct({
  diagram_id: Schema.String,
  classifier_local_id: Schema.String,
  attr_name: Schema.String,
})

export const DatatypeTypeUsagesSchema = Schema.Struct({
  type_id: Schema.String,
  usages: Schema.Array(DatatypeTypeUsageSchema),
})
export type DatatypeTypeUsages = typeof DatatypeTypeUsagesSchema.Type

export const AllocatedIdentifierSchema = Schema.Struct({ id: Schema.String })
export type AllocatedIdentifier = typeof AllocatedIdentifierSchema.Type

// ── Ontology ──────────────────────────────────────────────────────────────────

export const OntologyClassificationSchema = Schema.Struct({
  source_type: Schema.String,
  outgoing: Schema.Record({ key: Schema.String, value: Schema.Array(Schema.String) }),
  incoming: Schema.Record({ key: Schema.String, value: Schema.Array(Schema.String) }),
  symmetric: Schema.Record({ key: Schema.String, value: Schema.Array(Schema.String) }),
})
export type OntologyClassification = typeof OntologyClassificationSchema.Type

export const OntologyPairSchema = Schema.Struct({
  source_type: Schema.String,
  target_type: Schema.String,
  connection_types: Schema.Array(Schema.String),
  symmetric: Schema.Array(Schema.String),
  // Always present: the pair route builds it for every permitted type, with null where the ontology
  // assigns no kind. Optional here described a response the route does not send.
  relationship_kind_map: Schema.Record({
    key: Schema.String,
    value: Schema.NullOr(Schema.String),
  }),
})
export type OntologyPair = typeof OntologyPairSchema.Type

// ── Diagram refs ─────────────────────────────────────────────────────────────

export const DiagramRefSchema = Schema.Struct({
  artifact_id: Schema.String,
  name: Schema.String,
})
export type DiagramRef = typeof DiagramRefSchema.Type

export const DiagramRefsSchema = Schema.Array(DiagramRefSchema)
export type DiagramRefs = typeof DiagramRefsSchema.Type
