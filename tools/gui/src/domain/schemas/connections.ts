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

/**
 * The connections read, as the surface answers it: an object with `items`.
 *
 * Not a bare array — a top-level array has nowhere to put a total or a cursor without becoming a
 * second breaking change. The adapter unwraps it, so callers still see the list.
 */
export const ConnectionListResponseSchema = Schema.Struct({
  items: ConnectionListSchema,
})

/**
 * One connection in an entity's context, both endpoints already resolved.
 *
 * Declared in its own right rather than by extending `ConnectionRecordSchema`, which was the
 * shorter spelling and the wrong shape. That schema describes the *list* read, where several fields
 * are genuinely optional and two more (`specializations`, `metadata`) exist that a context row never
 * carries — so extending it made six always-present fields optional and added two that cannot
 * arrive. The context read fills every field from a `NOT NULL` index column.
 */
export const EntityContextConnectionSchema = Schema.Struct({
  artifact_id: Schema.String,
  source: Schema.String,
  target: Schema.String,
  conn_type: Schema.String,
  version: Schema.String,
  status: Schema.String,
  path: Schema.String,
  content_text: Schema.String,
  associated_entities: Schema.Array(Schema.String),
  src_multiplicity: Schema.String,
  tgt_multiplicity: Schema.String,
  specialization: Schema.String,
  source_name: Schema.String,
  target_name: Schema.String,
  source_artifact_type: Schema.String,
  target_artifact_type: Schema.String,
  source_domain: Schema.String,
  target_domain: Schema.String,
  source_scope: Schema.String,
  target_scope: Schema.String,
  /** Which end of the connection the entity being read is *not*. */
  other_entity_id: Schema.String,
  /** Which bucket this connection fell into. A closed vocabulary on the server, so it is one
   * here: a symmetric relation has no source-or-target answer, and a reader that treats the
   * value as free text has to reinvent that rule. */
  direction: Schema.Literal('outbound', 'inbound', 'symmetric'),
})
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
