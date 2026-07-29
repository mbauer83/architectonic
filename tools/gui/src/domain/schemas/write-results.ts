import { Schema } from 'effect'

export const WriteResultSchema = Schema.Struct({
  wrote: Schema.Boolean,
  path: Schema.String,
  artifact_id: Schema.String,
  content: Schema.NullOr(Schema.String),
  warnings: Schema.Array(Schema.String),
  verification: Schema.NullOr(Schema.Unknown),
})
export type WriteResult = typeof WriteResultSchema.Type

export const SyncDiagramToModelResultSchema = Schema.Struct({
  ...WriteResultSchema.fields,
  removed_entity_ids: Schema.Array(Schema.String),
  removed_connection_ids: Schema.Array(Schema.String),
})
export type SyncDiagramToModelResult = typeof SyncDiagramToModelResultSchema.Type
