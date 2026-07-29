import { Schema } from 'effect'

export const ArtifactChangeSchema = Schema.Struct({
  artifact_id: Schema.String,
  name: Schema.String,
  record_type: Schema.String,
  artifact_type: Schema.NullOr(Schema.String),
  file_status: Schema.String,
  changes: Schema.Array(Schema.String),
})
export type ArtifactChange = typeof ArtifactChangeSchema.Type

export const SyncChangesResultSchema = Schema.Struct({
  repo: Schema.String,
  artifacts: Schema.Array(ArtifactChangeSchema),
})
export type SyncChangesResult = typeof SyncChangesResultSchema.Type
