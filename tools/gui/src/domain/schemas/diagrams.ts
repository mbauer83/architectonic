import { Schema } from 'effect'
import { ViewpointApplicationSchema } from './viewpoints'
import { DiagramConnectionSchema, EntityContextConnectionSchema } from './connections'
import { EntitySummarySchema, EntityDisplayInfoSchema } from './entities'

export const DiagramDetailSchema = Schema.Struct({
  artifact_id: Schema.String,
  artifact_type: Schema.String,
  name: Schema.String,
  diagram_type: Schema.String,
  version: Schema.String,
  status: Schema.String,
  record_type: Schema.Literal('diagram'),
  path: Schema.String,
  is_global: Schema.optional(Schema.Boolean),
  content_snippet: Schema.String,
  puml_source: Schema.optional(Schema.String),
  rendered_filename: Schema.optional(Schema.NullOr(Schema.String)),
  entity_ids_used: Schema.optional(Schema.Array(Schema.String)),
  connection_ids_used: Schema.optional(Schema.Array(Schema.String)),
  diagram_entities: Schema.optional(Schema.Unknown),
  matrix_body: Schema.optional(Schema.String),
  extra: Schema.optional(Schema.Unknown),
  viewpoint: Schema.optional(Schema.NullOr(ViewpointApplicationSchema)),
})
export type DiagramDetail = typeof DiagramDetailSchema.Type

// ── Matrix diagram ───────────────────────────────────────────────────────────

export const MatrixConnTypeConfigSchema = Schema.Struct({
  conn_type: Schema.String,
  active: Schema.Boolean,
})
export type MatrixConnTypeConfig = typeof MatrixConnTypeConfigSchema.Type

export const MatrixConfigSchema = Schema.Struct({
  artifact_id: Schema.String,
  name: Schema.String,
  status: Schema.String,
  version: Schema.String,
  keywords: Schema.Array(Schema.String),
  entity_ids: Schema.Array(Schema.String),
  from_entity_ids: Schema.optional(Schema.NullOr(Schema.Array(Schema.String))),
  to_entity_ids: Schema.optional(Schema.NullOr(Schema.Array(Schema.String))),
  conn_type_configs: Schema.Array(MatrixConnTypeConfigSchema),
  combined: Schema.Boolean,
  matrix_body: Schema.String,
})
export type MatrixConfig = typeof MatrixConfigSchema.Type

export const MatrixPreviewResultSchema = Schema.Struct({
  markdown: Schema.String,
})
export type MatrixPreviewResult = typeof MatrixPreviewResultSchema.Type

export const C4NavLinkSchema = Schema.Struct({
  diagram_id: Schema.String,
  diagram_name: Schema.String,
  diagram_type: Schema.String,
  scope_entity_id: Schema.optional(Schema.NullOr(Schema.String)),
})
export type C4NavLink = typeof C4NavLinkSchema.Type

export const C4NavigationSchema = Schema.Struct({
  current_level: Schema.Number,
  scope_entity_id: Schema.NullOr(Schema.String),
  scope_entity_name: Schema.NullOr(Schema.String),
  parent_diagrams: Schema.Array(C4NavLinkSchema),
  child_diagrams: Schema.Array(C4NavLinkSchema),
})
export type C4Navigation = typeof C4NavigationSchema.Type

export const DiagramContextSchema = Schema.Struct({
  diagram: DiagramDetailSchema,
  entities: Schema.Array(EntitySummarySchema),
  connections: Schema.Array(DiagramConnectionSchema),
  candidate_connections: Schema.Array(EntityContextConnectionSchema),
  suggested_entities: Schema.Array(
    Schema.Struct({
      hop: Schema.Number,
      items: Schema.Array(EntityDisplayInfoSchema),
    }),
  ),
  explicit_connection_pairs: Schema.Array(Schema.Array(Schema.String)),
  generation: Schema.Number,
  etag: Schema.String,
  c4_navigation: Schema.optional(Schema.NullOr(C4NavigationSchema)),
})
export type DiagramContext = typeof DiagramContextSchema.Type

export const DiagramEntityDiscoverySchema = Schema.Struct({
  search_results: Schema.Array(EntityDisplayInfoSchema),
  candidate_connections: Schema.Array(EntityContextConnectionSchema),
  suggested_entities: Schema.Array(
    Schema.Struct({
      hop: Schema.Number,
      items: Schema.Array(EntityDisplayInfoSchema),
    }),
  ),
})
export type DiagramEntityDiscovery = typeof DiagramEntityDiscoverySchema.Type

export const DerivedEntitySchema = Schema.Struct({
  id: Schema.String,
  name: Schema.String,
  item_type: Schema.String,
})
export type DerivedEntity = typeof DerivedEntitySchema.Type

export const DiagramPreviewResultSchema = Schema.Struct({
  puml: Schema.String,
  image: Schema.NullOr(Schema.String),
  warnings: Schema.Array(Schema.String),
  derived_entities: Schema.NullOr(Schema.Array(DerivedEntitySchema)),
})
export type DiagramPreviewResult = typeof DiagramPreviewResultSchema.Type
