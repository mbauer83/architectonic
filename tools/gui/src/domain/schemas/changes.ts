import { Schema } from 'effect'

/**
 * One local change: an edit to an artifact this repository does not own, awaiting review upstream.
 *
 * `artifact_id` is the change's own — an artifact may carry more than one, so it is what discarding
 * names. `reference_id` is how this repository addresses the artifact, and therefore what a link
 * goes to; the enterprise id is what the change is *against* and is not something a client can open.
 */
export const ChangeSummarySchema = Schema.Struct({
  artifact_id: Schema.String,
  target_id: Schema.String,
  target_name: Schema.String,
  reference_id: Schema.NullOr(Schema.String),
  kind: Schema.Literal('entity', 'document', 'diagram'),
  changed_fields: Schema.Array(Schema.String),
  state: Schema.Literal('draft', 'submitted'),
  // Computed on read: `stale` means the enterprise artifact has moved since the change was written.
  condition: Schema.Literal('current', 'stale', 'conflicting'),
})
export type ChangeSummary = typeof ChangeSummarySchema.Type

export const ChangeListSchema = Schema.Struct({
  changes: Schema.Array(ChangeSummarySchema),
  total: Schema.Number,
})
export type ChangeList = typeof ChangeListSchema.Type

export const ChangeDiscardedSchema = Schema.Struct({
  artifact_id: Schema.String,
  discarded: Schema.Boolean,
  state: Schema.Literal('abandoned'),
})
export type ChangeDiscarded = typeof ChangeDiscardedSchema.Type
