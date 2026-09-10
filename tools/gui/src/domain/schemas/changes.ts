import { Schema } from 'effect'

/**
 * One local change: an edit to an artifact this repository does not own, held here until it is
 * submitted for review upstream.
 *
 * `artifact_id` is the change's own — an artifact may carry more than one, so it is what discarding
 * names. `target_id` is the promoted artifact, which is what a link goes to and what a reader knows.
 * The local reference standing for it is machinery and is deliberately not published.
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

/**
 * Where one change stood when a rebase rehearsed it, and what was done about it.
 *
 * `reason` is what a reader acts on — for a conflict it is the verifier's own refusal, because a
 * second wording of a refusal is a second vocabulary for the same thing.
 */
export const RebasedChangeSchema = Schema.Struct({
  artifact_id: Schema.String,
  target_id: Schema.String,
  outcome: Schema.Literal('clean', 'superseded', 'conflicting'),
  reason: Schema.String,
  restamped: Schema.Boolean,
})
export type RebasedChange = typeof RebasedChangeSchema.Type

export const ChangeRebasedSchema = Schema.Struct({
  changes: Schema.Array(RebasedChangeSchema),
  /**
   * The replacement review branch a rebase of a submitted set was published on. Null for a draft,
   * which has no published branch to replace — the branch is the unit of review, so a set already
   * under review gets a new one rather than having the one a reviewer is reading rewritten.
   */
  republished_branch: Schema.NullOr(Schema.String),
  summary: Schema.String,
})
export type ChangeRebased = typeof ChangeRebasedSchema.Type
