import { Schema } from 'effect'

/**
 * The authoring-time vocabulary the criteria editor offers: which entity and connection
 * types exist, which attribute paths are addressable and what they hold, and which bindings,
 * parameter types and derivation strategies the server will accept.
 *
 * Kept apart from the execution schemas next door because they answer different questions at
 * different times. These describe what a viewpoint *may* say and are fetched once to populate
 * pickers; those describe what one execution returned. Nothing here appears in a result.
 */

const BindingCatalogSchema = Schema.Struct({
  select: Schema.Array(Schema.String),
  aggregate: Schema.Array(Schema.String),
  result_types: Schema.Array(Schema.String),
})

const ParameterCatalogSchema = Schema.Struct({ types: Schema.Array(Schema.String) })

const DerivedCatalogSchema = Schema.Struct({
  traversal: Schema.Array(Schema.String),
  certainty: Schema.Array(Schema.String),
  reduce: Schema.Array(Schema.String),
})

const ConnectionDerivationEntrySchema = Schema.Struct({ role: Schema.String, strength: Schema.NullOr(Schema.Number) })

export const CriteriaCatalogSchema = Schema.Struct({
  entity_types: Schema.Array(Schema.String),
  connection_types: Schema.Array(Schema.String),
  specialization_slugs: Schema.Array(Schema.String),
  entity_attribute_types: Schema.Record({ key: Schema.String, value: Schema.String }),
  connection_attribute_types: Schema.Record({ key: Schema.String, value: Schema.String }),
  // Enumerable value sets per attribute path (schema-declared `enum` attributes, plus the
  // enumerable reserved facets `domain`/`status`) — drives the criteria value picker's
  // switch from free text to a dropdown / multi-select. Optional-with-default so the editor
  // tolerates a backend that predates this field (falls back to free-text everywhere).
  entity_attribute_enums: Schema.optionalWith(
    Schema.Record({ key: Schema.String, value: Schema.Array(Schema.String) }),
    { default: () => ({}) },
  ),
  connection_attribute_enums: Schema.optionalWith(
    Schema.Record({ key: Schema.String, value: Schema.Array(Schema.String) }),
    { default: () => ({}) },
  ),
  symmetric_connection_types: Schema.Array(Schema.String),
  reserved_entity_paths: Schema.Array(Schema.String),
  reserved_connection_paths: Schema.Array(Schema.String),
  depth_cap: Schema.Number,
  // entity type slug -> owning domain (hierarchy[0]) — lets the scope picker group entity
  // types by domain and support "exclude this whole domain" bulk actions.
  entity_type_domains: Schema.Record({ key: Schema.String, value: Schema.String }),
  // Registries snapshot for the bindings/parameters/derived-attribute panels' own pickers —
  // same "one snapshot, every picker" convention as the entity/connection type lists above.
  bindings: BindingCatalogSchema,
  parameters: ParameterCatalogSchema,
  derived: DerivedCatalogSchema,
  connection_derivation: Schema.Record({ key: Schema.String, value: ConnectionDerivationEntrySchema }),
})
export type CriteriaCatalog = typeof CriteriaCatalogSchema.Type
