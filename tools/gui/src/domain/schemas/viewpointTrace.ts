/**
 * Coverage-trace result contract: the discriminated pattern-result union and the table that
 * carries it. Split from `viewpoints.ts` to keep both modules within the size policy — this
 * is a self-contained contract that only the coverage surfaces consume.
 */
import { Schema } from 'effect'

/** One obligation the trace could not satisfy. `kind` is the discriminator — without it a
 * shortcut is indistinguishable from an outcome-less terminal, and a missing outcome from a
 * missing requirement. */
export const TraceObligationSchema = Schema.Struct({
  kind: Schema.Literal('requirement', 'shortcut', 'missing-requirement', 'missing-outcome'),
  root_id: Schema.String,
  requirement_id: Schema.optional(Schema.String),
  outcome_id: Schema.optional(Schema.String),
  via_outcome_id: Schema.optional(Schema.NullOr(Schema.String)),
})
export type TraceObligation = typeof TraceObligationSchema.Type

/** Discriminated by `role`. An authoritative pattern carries a verdict; a diagnostic one
 * carries only an observation — its absence (`none_observed`) is verdict-NEUTRAL and must
 * never be rendered as a pass or a gap. */
export const AuthoritativePatternResultSchema = Schema.Struct({
  role: Schema.Literal('authoritative'),
  verdict: Schema.Literal('pass', 'gap', 'not_applicable'),
  status_code: Schema.String,
  coverage: Schema.Struct({ covered: Schema.Number, applicable: Schema.Number }),
  incomplete_branch_count: Schema.Number,
  failing_obligations: Schema.Array(TraceObligationSchema),
  failing_overflow: Schema.Number,
  last_satisfied_ids: Schema.Array(Schema.String),
  missing_expected: Schema.Array(Schema.String),
  shortcut: Schema.Boolean,
  diagnostic_code: Schema.optionalWith(Schema.NullOr(Schema.String), { default: () => null }),
})

export const DiagnosticPatternResultSchema = Schema.Struct({
  role: Schema.Literal('diagnostic'),
  observation: Schema.Literal('observed', 'none_observed', 'not_applicable'),
  last_satisfied_ids: Schema.Array(Schema.String),
})

export const PatternResultSchema = Schema.Union(
  AuthoritativePatternResultSchema,
  DiagnosticPatternResultSchema,
)
export type PatternResult = typeof PatternResultSchema.Type

export const TraceRowSchema = Schema.Struct({
  entity_id: Schema.String,
  entity_type: Schema.String,
  name: Schema.String,
  tier: Schema.String,
  verdict: Schema.Literal('pass', 'gap', 'not_applicable'),
  /** `[patternName, result]` pairs in declaration order. */
  pattern_results: Schema.Array(Schema.Tuple(Schema.String, PatternResultSchema)),
})
export type TraceRow = typeof TraceRowSchema.Type

/** Present only for a viewpoint declaring `trace_patterns`. Rows arrive already
 * verdict-filtered, gaps-first sorted and paged; `total_rows` counts the applicable
 * population BEFORE the page limit, so a gap beyond the page still registers. */
export const TraceTableSchema = Schema.Struct({
  rows: Schema.Array(TraceRowSchema),
  total_rows: Schema.Number,
  returned_rows: Schema.Number,
  truncated: Schema.Boolean,
  derived_truncated: Schema.Boolean,
})
export type TraceTable = typeof TraceTableSchema.Type
