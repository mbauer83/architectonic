import { Schema } from 'effect'

/**
 * Decoders for the FMEA projection of an analysis.
 *
 * The view declared these as three interfaces of its own. Two of them were looser than the route:
 * `element_name` and `element_type` were optional for a route that always sends them (empty when the
 * architecture model cannot describe the element, which is a value and not an absence), and
 * `dismissal` had both its fields optional.
 *
 * `indeterminate` is a member of the action-priority band, not an absence. That is the one confusion
 * this grid must never permit — an unrated cell reading as a low-priority one — so the vocabulary is
 * closed here and checked against what the backend publishes.
 */
export const ACTION_PRIORITIES = ['high', 'medium', 'low', 'indeterminate'] as const
export type ActionPriority = (typeof ACTION_PRIORITIES)[number]

export const ASSESSMENT_STATES = ['untouched', 'not-credible', 'recorded'] as const
export type AssessmentState = (typeof ASSESSMENT_STATES)[number]

/** One recorded judgement about a factor — the same shape whether it still applies or not. */
export const FmeaFactorAssessmentSchema = Schema.Struct({
  value: Schema.String,
  author: Schema.String,
  justification: Schema.String,
})

/** One factor's effective value. `value` is null where the factor has none a reader should act on —
 *  occurrence is asserted-only, so there is no derived value to fall back to. */
export const FmeaFactorSchema = Schema.Struct({
  value: Schema.NullOr(Schema.String),
  basis: Schema.String,
  // The digest of the model inputs the derived value came from. A judgement has to be filed against
  // it, because one filed against a basis that has since moved no longer applies.
  basis_digest: Schema.String,
  // The judgement the value *is*, where a person made one that still applies. Null for a derived
  // value: nobody asserted it, so there is no rationale to show.
  assessment: Schema.NullOr(FmeaFactorAssessmentSchema),
  superseded: Schema.NullOr(FmeaFactorAssessmentSchema),
})
export type FmeaFactor = typeof FmeaFactorSchema.Type

/** Both fields empty on a cell that was not dismissed. Dismissing is a judgement with an author and
 *  a reason, and it counts as coverage. */
export const FmeaCellDismissalSchema = Schema.Struct({
  by: Schema.String,
  reason: Schema.String,
})

export const FmeaCellSchema = Schema.Struct({
  guideword: Schema.String,
  state: Schema.Literal(...ASSESSMENT_STATES),
  // Null for a cell no failure mode has been written against: the absence *is* the untouched state.
  node_id: Schema.NullOr(Schema.String),
  action_priority: Schema.Literal(...ACTION_PRIORITIES),
  occurrence_is_requested: Schema.Boolean,
  // Facts the model already knows, for a rationale someone is about to write. Nothing here proposes
  // a rank, which is why a form may pre-fill the rationale and must never pre-fill the value.
  occurrence_rationale_draft: Schema.String,
  next_action: Schema.String,
  dismissal: FmeaCellDismissalSchema,
  factors: Schema.Record({ key: Schema.String, value: FmeaFactorSchema }),
})
export type FmeaCell = typeof FmeaCellSchema.Type

export const FmeaMatrixRowSchema = Schema.Struct({
  element_id: Schema.String,
  // Empty when the architecture model cannot describe the element. The row still exists, keyed by id.
  element_name: Schema.String,
  element_type: Schema.String,
  nominated_by: Schema.Array(Schema.String),
  cells: Schema.Array(FmeaCellSchema),
  // Both stated rather than one and a total: a dismissal counts as answered, so the split is the
  // coverage figure and deriving it from a length would get it wrong.
  answered_cells: Schema.Number,
  unanswered_cells: Schema.Number,
  worst_action_priority: Schema.NullOr(Schema.Literal(...ACTION_PRIORITIES)),
})
export type FmeaMatrixRow = typeof FmeaMatrixRowSchema.Type

export const FmeaMatrixSchema = Schema.Struct({
  analysis_id: Schema.String,
  rows: Schema.Array(FmeaMatrixRowSchema),
  count: Schema.Number,
  // Travels with the matrix: a recording surface offers the members of the scale and nothing else,
  // and restating an ordinal set whose order is load-bearing would be a second source of truth.
  occurrence_scale: Schema.Array(Schema.String),
})
export type FmeaMatrix = typeof FmeaMatrixSchema.Type

export const decodeFmeaMatrix = (body: unknown): FmeaMatrix =>
  Schema.decodeUnknownSync(FmeaMatrixSchema)(body)
