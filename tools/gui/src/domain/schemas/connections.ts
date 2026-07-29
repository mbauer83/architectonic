import { Schema } from 'effect'

export const ConnectionRecordSchema = Schema.Struct({
  artifact_id: Schema.String,
  source: Schema.String,
  target: Schema.String,
  source_name: Schema.optional(Schema.String),
  target_name: Schema.optional(Schema.String),
  conn_type: Schema.String,
  version: Schema.String,
  status: Schema.String,
  path: Schema.String,
  content_text: Schema.String,
  src_multiplicity: Schema.optional(Schema.String),
  tgt_multiplicity: Schema.optional(Schema.String),
  specialization: Schema.optional(Schema.String),
  specializations: Schema.optional(Schema.Array(Schema.String)),
  metadata: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  associated_entities: Schema.optional(Schema.Array(Schema.String)),
})
export type ConnectionRecord = typeof ConnectionRecordSchema.Type

export const ConnectionListSchema = Schema.Array(ConnectionRecordSchema)
export type ConnectionList = typeof ConnectionListSchema.Type

export const EntityContextConnectionSchema = Schema.extend(
  ConnectionRecordSchema,
  Schema.Struct({
    source_artifact_type: Schema.String,
    target_artifact_type: Schema.String,
    source_domain: Schema.String,
    target_domain: Schema.String,
    source_scope: Schema.String,
    target_scope: Schema.String,
    other_entity_id: Schema.String,
    direction: Schema.String,
  }),
)
export type EntityContextConnection = typeof EntityContextConnectionSchema.Type

// ── Diagram preview result ────────────────────────────────────────────────────

export const DiagramConnectionSchema = Schema.Struct({
  artifact_id: Schema.String,
  source: Schema.String,
  target: Schema.String,
  conn_type: Schema.String,
  version: Schema.String,
  status: Schema.String,
  path: Schema.String,
  content_text: Schema.String,
  source_name: Schema.String,
  target_name: Schema.String,
  source_alias: Schema.NullOr(Schema.String),
  target_alias: Schema.NullOr(Schema.String),
  edge_key: Schema.optional(Schema.NullOr(Schema.String)),
  edge_label_override: Schema.optional(Schema.NullOr(Schema.String)),
  // Set only for the ephemeral viewpoint-diagram viewer's derived connections (a real
  // persisted diagram's connections are always modeled, never composed) — `certainty`
  // non-null is what the sidebar uses to decide whether to offer the witness chain.
  certainty: Schema.optional(Schema.NullOr(Schema.Literal('certain', 'potential'))),
  hops: Schema.optional(Schema.NullOr(Schema.Number)),
  via_connection_ids: Schema.optional(Schema.Array(Schema.String)),
})
export type DiagramConnection = typeof DiagramConnectionSchema.Type
