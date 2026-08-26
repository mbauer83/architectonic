import { Schema } from 'effect'
import { DiagramRefSchema } from './diagram-types'
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

/**
 * One row of the entity list: enough to render, filter, link and badge.
 *
 * Exactly the fields the list read serves. It used to carry seven more — `display_alias` and six
 * hierarchy keys — none of which any route sends and only one of which anything read. The alias is
 * resolved by a *diagram* read, so it belongs to `DiagramContextEntitySchema`; the six hierarchy
 * keys had no producer and no consumer at all.
 *
 * `last_updated` is absent-or-value rather than nullable: this read omits its unset optionals, so a
 * stampless artifact has no key rather than a null one.
 */
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
  conn_in: Schema.optional(Schema.Number),
  conn_sym: Schema.optional(Schema.Number),
  conn_out: Schema.optional(Schema.Number),
  group: Schema.optional(Schema.String),
  specializations: Schema.Array(Schema.String),
  last_updated: Schema.optional(Schema.String),
})
export type EntitySummary = typeof EntitySummarySchema.Type

export const EntityListSchema = Schema.Struct({
  total: Schema.Number,
  items: Schema.Array(EntitySummarySchema),
})
export type EntityList = typeof EntityListSchema.Type

// ── Entity detail (read view) ─────────────────────────────────────────────────

/** A document that cites this entity, and the link it cites it through. */
export const DocumentReferenceSchema = Schema.Struct({
  document_id: Schema.String,
  title: Schema.String,
  doc_type: Schema.String,
  path: Schema.String,
  section: Schema.String,
  label: Schema.String,
  href: Schema.String,
})
export type DocumentReference = typeof DocumentReferenceSchema.Type

/**
 * One entity, with its parsed content sections and its degree.
 *
 * The seven collection-valued fields are *not* optional: the DTO gives each a default, so every read
 * carries all of them and declaring them optional made every reader write a fallback for a case the
 * server cannot produce. `attributes` — the record's own typed attribute map — was missing here
 * entirely, and `properties` (the parsed content table) was being read in its place.
 */
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
  content_snippet: Schema.optional(Schema.String),
  keywords: Schema.Array(Schema.String),
  summary: Schema.optional(Schema.String),
  properties: Schema.Record({ key: Schema.String, value: Schema.Unknown }),
  attributes: Schema.Record({ key: Schema.String, value: Schema.Unknown }),
  notes: Schema.optional(Schema.String),
  group: Schema.optional(Schema.String),
  last_updated: Schema.optional(Schema.String),
  specializations: Schema.Array(Schema.String),
  is_global: Schema.optional(Schema.Boolean),
  host_diagram_id: Schema.optional(Schema.String),
  conn_in: Schema.optional(Schema.Number),
  conn_sym: Schema.optional(Schema.Number),
  conn_out: Schema.optional(Schema.Number),
  content_text: Schema.optional(Schema.String),
  display_blocks: Schema.Record({ key: Schema.String, value: Schema.String }),
  extra: Schema.Record({ key: Schema.String, value: Schema.Unknown }),
  referenced_in_documents: Schema.Array(DocumentReferenceSchema),
  referenced_in_diagrams: Schema.Array(DiagramRefSchema),
})
export type EntityDetail = typeof EntityDetailSchema.Type

/**
 * An entity detail whose Markdown has been rendered.
 *
 * `content_html` is the client's own field: the server sends `content_text` and the adapter renders
 * it. Declaring it on `EntityDetailSchema` put a field no response carries into the response
 * contract, and no assertion against the published document could then hold.
 */
export type RenderedEntityDetail = EntityDetail & { readonly content_html?: string }

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

/** A context read whose entity's Markdown has been rendered — see {@link RenderedEntityDetail}. */
export type RenderedEntityContext = Omit<EntityContext, 'entity'> & {
  readonly entity: RenderedEntityDetail
}

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
  //: What the value addresses, where it addresses something rather than merely matching a shape.
  //: `uri` is the one the ontology declares; an authoring input renders such an attribute as a
  //: reference. Absent for an attribute that declares no format, which is most of them.
  format: Schema.optional(Schema.String),
  enum: Schema.optional(Schema.Array(Schema.String)),
  default: Schema.optional(Schema.String),
  constraints: Schema.optional(EntityAttributeConstraintsSchema),
  items: Schema.optional(EntityAttributeItemDescriptorSchema),
})
export type EntityAttributeDescriptor = typeof EntityAttributeDescriptorSchema.Type

export const EntitySchemaInfoSchema = Schema.Struct({
  artifact_type: Schema.String,
  specialization: Schema.String,
  /** Absent when no schema file declares one for this type — which is the whole of what the
   * missing key says, so it is absent rather than null. */
  schema: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  properties: Schema.Array(Schema.String),
  required: Schema.Array(Schema.String),
  descriptors: Schema.Record({ key: Schema.String, value: EntityAttributeDescriptorSchema }),
  conflicts: Schema.Array(Schema.String),
  // Derived read of the SAME conflicts channel, not a parallel one: true means the write
  // boundary will refuse a create/edit for this (type, specialization) pair.
  quarantined: Schema.Boolean,
})
export type EntitySchemaInfo = typeof EntitySchemaInfoSchema.Type
