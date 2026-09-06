import { Schema } from 'effect'

/**
 * One local change: an edit to an artifact this repository does not own, awaiting review upstream.
 *
 * `artifact_id` is the change's own — an artifact may carry more than one, so it is what discarding
 * names. `reference_id` is how this repository addresses the artifact, and therefore what a link
 * goes to; the enterprise id is what the change is *against* and is not something a client can open.
 */
/**
 * One field of a stale change: what it asks for, and what the artifact says now.
 *
 * Both null where the value has no single line to show — a properties table, an attribute-type map.
 * Naming the field is still worth saying; a rendering invented for the list would be a second,
 * worse spelling of what the artifact view already draws.
 */
export const FieldDivergenceSchema = Schema.Struct({
  field: Schema.String,
  proposed: Schema.NullOr(Schema.String),
  current: Schema.NullOr(Schema.String),
})
export type FieldDivergence = typeof FieldDivergenceSchema.Type

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
  /** What the change asks for beside what the artifact says now. Empty unless it is stale. */
  divergence: Schema.Array(FieldDivergenceSchema),
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
