import { Schema } from 'effect'
import { EntityContextConnectionSchema } from './connections'

// ── Neighbors ────────────────────────────────────────────────────────────────

export const NeighborsSchema = Schema.Record({ key: Schema.String, value: Schema.Array(Schema.String) })
export type Neighbors = typeof NeighborsSchema.Type

/**
 * The direct arm of the neighbourhood response.
 *
 * The two arms — stated connections against derived relationships — are genuinely different
 * answers, and the direct one used to arrive untagged, so a client could not tell which it had
 * received. `traversal` is now the discriminator.
 */
export const DirectNeighborhoodSchema = Schema.Struct({
  traversal: Schema.Literal('direct'),
  hops: NeighborsSchema,
})
export type DirectNeighborhood = typeof DirectNeighborhoodSchema.Type

export const EntitySummarySchema = Schema.Struct({
  artifact_id: Schema.String,
  artifact_type: Schema.String,
  name: Schema.String,
  version: Schema.String,
  status: Schema.String,
  domain: Schema.String,
  subdomain: Schema.String,
  path: Schema.String,
  is_global: Schema.Boolean,
  host_diagram_id: Schema.optional(Schema.String),
  display_alias: Schema.optional(Schema.String),
  parent_entity_id: Schema.optional(Schema.NullOr(Schema.String)),
  hierarchy_relation_type: Schema.optional(Schema.String),
  hierarchy_depth: Schema.optional(Schema.Number),
  parent_specialization_id: Schema.optional(Schema.NullOr(Schema.String)),
  specialization_depth: Schema.optional(Schema.Number),
  all_parents: Schema.optional(Schema.Array(Schema.Struct({
    parent_id: Schema.String,
    relation_type: Schema.String,
  }))),
  conn_in: Schema.optional(Schema.Number),
  conn_sym: Schema.optional(Schema.Number),
  conn_out: Schema.optional(Schema.Number),
  group: Schema.optional(Schema.String),
  specialization: Schema.optional(Schema.String),
  // When the artifact was last written (UTC ISO-8601). Null for artifacts with no stamp:
  // diagram-only entities and repositories predating the field.
  last_updated: Schema.optional(Schema.NullOr(Schema.String)),
})
export type EntitySummary = typeof EntitySummarySchema.Type

export const EntityListSchema = Schema.Struct({
  total: Schema.Number,
  items: Schema.Array(EntitySummarySchema),
})
export type EntityList = typeof EntityListSchema.Type

// ── Entity detail (read view) ─────────────────────────────────────────────────

export const EntityDetailSchema = Schema.Struct({
  artifact_id: Schema.String,
  artifact_type: Schema.String,
  name: Schema.String,
  version: Schema.String,
  status: Schema.String,
  domain: Schema.String,
  subdomain: Schema.String,
  record_type: Schema.Literal('entity'),
  path: Schema.String,
  content_snippet: Schema.String,
  keywords: Schema.optional(Schema.Array(Schema.String)),
  summary: Schema.optional(Schema.String),
  properties: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  notes: Schema.optional(Schema.String),
  specialization: Schema.optional(Schema.String),
  specializations: Schema.optional(Schema.Array(Schema.String)),
  is_global: Schema.optional(Schema.Boolean),
  host_diagram_id: Schema.optional(Schema.String),
  conn_in: Schema.optional(Schema.Number),
  conn_sym: Schema.optional(Schema.Number),
  conn_out: Schema.optional(Schema.Number),
  content_text: Schema.optional(Schema.String),
  content_html: Schema.optional(Schema.String),
  display_blocks: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.String })),
  extra: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  referenced_in_documents: Schema.optional(Schema.Array(Schema.Struct({
    document_id: Schema.String,
    title: Schema.String,
    doc_type: Schema.String,
    path: Schema.String,
    section: Schema.String,
    label: Schema.String,
    href: Schema.String,
  }))),
})
export type EntityDetail = typeof EntityDetailSchema.Type

export const EntityContextSchema = Schema.Struct({
  entity: EntityDetailSchema,
  connections: Schema.Struct({
    outbound: Schema.Array(EntityContextConnectionSchema),
    inbound: Schema.Array(EntityContextConnectionSchema),
    symmetric: Schema.Array(EntityContextConnectionSchema),
  }),
  counts: Schema.Struct({
    conn_in: Schema.Number,
    conn_out: Schema.Number,
    conn_sym: Schema.Number,
  }),
  generation: Schema.Number,
  etag: Schema.String,
})
export type EntityContext = typeof EntityContextSchema.Type

// ── Entity display info (diagram create form) ────────────────────────────────

export const EntityDisplayInfoSchema = Schema.Struct({
  artifact_id: Schema.String,
  name: Schema.String,
  artifact_type: Schema.String,
  domain: Schema.String,
  subdomain: Schema.String,
  status: Schema.String,
  /** The PlantUML alias the entity is drawn under; always present. */
  display_alias: Schema.String,
  element_type: Schema.String,
  element_label: Schema.String,
  /** Diagram-owned construct (swimlane, C4 person, …) — pickable, but rendered below a
   * "diagram-internal" divider, never interleaved with model entities. */
  diagram_internal: Schema.optionalWith(Schema.Boolean, { default: () => false }),
})
export type EntityDisplayInfo = typeof EntityDisplayInfoSchema.Type

export const EntityDisplaySearchResultSchema = Schema.Struct({
  items: Schema.Array(EntityDisplayInfoSchema),
  next_cursor: Schema.NullOr(Schema.String),
})
export type EntityDisplaySearchResult = typeof EntityDisplaySearchResultSchema.Type

// ── Entity taxonomy ───────────────────────────────────────────────────────────

export const EntityTaxonomyTypeSchema = Schema.Struct({
  name: Schema.String,
  count: Schema.Number,
})
export type EntityTaxonomyType = typeof EntityTaxonomyTypeSchema.Type

export const EntityTaxonomyDomainSchema = Schema.Struct({
  name: Schema.String,
  count: Schema.Number,
  types: Schema.Array(EntityTaxonomyTypeSchema),
})
export type EntityTaxonomyDomain = typeof EntityTaxonomyDomainSchema.Type

export const EntityTaxonomySchema = Schema.Struct({
  domains: Schema.Array(EntityTaxonomyDomainSchema),
})
export type EntityTaxonomy = typeof EntityTaxonomySchema.Type

// ── Entity attribute schemata ─────────────────────────────────────────────────

const EntityAttributeConstraintsSchema = Schema.Struct({
  minimum: Schema.optional(Schema.Number),
  maximum: Schema.optional(Schema.Number),
  exclusiveMinimum: Schema.optional(Schema.Number),
  exclusiveMaximum: Schema.optional(Schema.Number),
  minLength: Schema.optional(Schema.Number),
  maxLength: Schema.optional(Schema.Number),
  pattern: Schema.optional(Schema.String),
})

// An array attribute's per-item schema, so a list editor can type each element. One level
// deep — array-of-array is not an authoring shape we support — so this is not the recursive
// descriptor type but a flat item type.
export const EntityAttributeItemDescriptorSchema = Schema.Struct({
  type: Schema.String,
  enum: Schema.optional(Schema.Array(Schema.String)),
  constraints: Schema.optional(EntityAttributeConstraintsSchema),
})
export type EntityAttributeItemDescriptor = typeof EntityAttributeItemDescriptorSchema.Type

export const EntityAttributeDescriptorSchema = Schema.Struct({
  type: Schema.String,
  enum: Schema.optional(Schema.Array(Schema.String)),
  default: Schema.optional(Schema.String),
  constraints: Schema.optional(EntityAttributeConstraintsSchema),
  items: Schema.optional(EntityAttributeItemDescriptorSchema),
})
export type EntityAttributeDescriptor = typeof EntityAttributeDescriptorSchema.Type

export const EntitySchemaInfoSchema = Schema.Struct({
  artifact_type: Schema.String,
  specialization: Schema.optional(Schema.String),
  schema: Schema.NullOr(Schema.Unknown),
  properties: Schema.Array(Schema.String),
  required: Schema.Array(Schema.String),
  descriptors: Schema.Record({ key: Schema.String, value: EntityAttributeDescriptorSchema }),
  conflicts: Schema.optional(Schema.Array(Schema.String)),
  // Derived read of the SAME conflicts channel, not a parallel one: true means the write
  // boundary will refuse a create/edit for this (type, specialization) pair.
  quarantined: Schema.optional(Schema.Boolean),
})
export type EntitySchemaInfo = typeof EntitySchemaInfoSchema.Type
