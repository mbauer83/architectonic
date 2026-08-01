/**
 * Coverage-trace result contract: the discriminated pattern-result union and the table that
 * carries it. Split from `viewpoints.ts` to keep both modules within the size policy — this
 * is a self-contained contract that only the coverage surfaces consume.
 */
import { Schema } from 'effect'

/** One obligation the trace could not satisfy, discriminated by `kind`.
 *
 * Four arms rather than one struct with four optional id fields: each arm carries a
 * different pair of ids, and the flat shape let a reader take `requirement_id` off an
 * obligation that has none. `via_outcome_id` is null on an outcome-rooted terminal —
 * there is no intermediate hop, not an unknown one. */
export const TerminalObligationSchema = Schema.Struct({
  kind: Schema.Literal('requirement'),
  root_id: Schema.String,
  requirement_id: Schema.String,
  via_outcome_id: Schema.NullOr(Schema.String),
})

export const ShortcutObligationSchema = Schema.Struct({
  kind: Schema.Literal('shortcut'),
  root_id: Schema.String,
  requirement_id: Schema.String,
})

export const MissingRequirementObligationSchema = Schema.Struct({
  kind: Schema.Literal('missing-requirement'),
  root_id: Schema.String,
  outcome_id: Schema.String,
})

export const MissingOutcomeObligationSchema = Schema.Struct({
  kind: Schema.Literal('missing-outcome'),
  root_id: Schema.String,
})

export const TraceObligationSchema = Schema.Union(
  TerminalObligationSchema,
  ShortcutObligationSchema,
  MissingRequirementObligationSchema,
  MissingOutcomeObligationSchema,
)
export type TraceObligation = typeof TraceObligationSchema.Type

/** Discriminated by `role`. An authoritative pattern carries a verdict; a diagnostic one
 * carries only an observation — its absence (`none_observed`) is verdict-NEUTRAL and must
 * never be rendered as a pass or a gap. */
export const AuthoritativePatternResultSchema = Schema.Struct({
  role: Schema.Literal('authoritative'),
  verdict: Schema.Literal('pass', 'gap', 'not_applicable'),
  /** The worst status that applied, by the registry's fixed precedence. A closed
   * vocabulary on the server, so it is one here too: a status added there without one
   * here is a compile error rather than a value no branch handles. */
  status_code: Schema.Literal(
    'ok', 'shortcut', 'incomplete_branch', 'partial_branches', 'no_trace',
    'ambiguous_link', 'cycle', 'observed', 'none_observed', 'not_applicable',
  ),
  coverage: Schema.Struct({ covered: Schema.Number, applicable: Schema.Number }),
  incomplete_branch_count: Schema.Number,
  failing_obligations: Schema.Array(TraceObligationSchema),
  failing_overflow: Schema.Number,
  last_satisfied_ids: Schema.Array(Schema.String),
  missing_expected: Schema.Array(Schema.String),
  shortcut: Schema.Boolean,
  diagnostic_code: Schema.NullOr(Schema.Literal('cycle', 'budget_aborted', 'ambiguous_link')),
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
