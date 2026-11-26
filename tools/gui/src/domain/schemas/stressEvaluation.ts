import { Schema } from 'effect'

/**
 * A stress analysis's test set (`/api/stress-analyses/{id}/test-set`), a candidate's residuality in each
 * analysis that judged it (`/api/candidates/{id}/residuality`), and the perspectives offered to
 * whoever writes stressors (`/api/stress-perspectives`).
 */

export const VerdictSchema = Schema.Literal('survives', 'degrades', 'fails')
export type Verdict = typeof VerdictSchema.Type

const HeldApartStressorSchema = Schema.Struct({
  id: Schema.String,
  stressor: Schema.String,
  kind: Schema.optional(Schema.String),
  usable: Schema.Boolean,
  unusable_reason: Schema.optional(Schema.String),
})
export type HeldApartStressor = typeof HeldApartStressorSchema.Type

const StressVerdictSchema = Schema.Struct({
  id: Schema.String,
  stressor: Schema.String,
  architecture: Schema.String,
  verdict: Schema.optional(VerdictSchema),
  usable: Schema.Boolean,
  reasoning: Schema.String,
})
export type StressVerdict = typeof StressVerdictSchema.Type

export const ArchitectureStandingSchema = Schema.Struct({
  architecture: Schema.String,
  integrated: Schema.Boolean,
  usable: Schema.Number,
  judged: Schema.Number,
  survives: Schema.Number,
  degrades: Schema.Number,
  fails: Schema.Number,
  naive_survives: Schema.Number,
  residuality: Schema.optional(Schema.Number),
  strict: Schema.optional(Schema.Number),
})
export type ArchitectureStanding = typeof ArchitectureStandingSchema.Type

export const AnalysisEvaluationSchema = Schema.Struct({
  document: Schema.String,
  naive_candidate: Schema.String,
  design_stressors: Schema.Number,
  stressors: Schema.Array(HeldApartStressorSchema),
  verdicts: Schema.Array(StressVerdictSchema),
  unwritten_perspectives: Schema.Array(Schema.String),
  architectures: Schema.Array(ArchitectureStandingSchema),
  stage: Schema.Struct({
    naive_judged: Schema.Boolean,
    adapted: Schema.Boolean,
    integrated: Schema.Boolean,
    integration_judged: Schema.Boolean,
  }),
})
export type AnalysisEvaluation = typeof AnalysisEvaluationSchema.Type

export const HeldOutSchema = Schema.Struct({
  document: Schema.String,
  seed: Schema.Number,
  dry_run: Schema.Boolean,
  wrote: Schema.Boolean,
  design_stressors: Schema.Number,
  held_out: Schema.Array(Schema.String),
})
export type HeldOut = typeof HeldOutSchema.Type

const AnalysisStandingSchema = Schema.Struct({
  ...ArchitectureStandingSchema.fields,
  document: Schema.String,
  title: Schema.String,
})
export type AnalysisStanding = typeof AnalysisStandingSchema.Type

export const CandidateResidualitySchema = Schema.Struct({
  candidate: Schema.String,
  analyses: Schema.Array(AnalysisStandingSchema),
})
export type CandidateResiduality = typeof CandidateResidualitySchema.Type

const StressPerspectiveSchema = Schema.Struct({
  id: Schema.String, name: Schema.String, kind: Schema.String, question: Schema.String,
})
export type StressPerspective = typeof StressPerspectiveSchema.Type

const PerspectiveFrameworkSchema = Schema.Struct({
  id: Schema.String, name: Schema.String, perspectives: Schema.Array(StressPerspectiveSchema),
})
export type PerspectiveFramework = typeof PerspectiveFrameworkSchema.Type

export const StressPerspectivesSchema = Schema.Struct({ frameworks: Schema.Array(PerspectiveFrameworkSchema) })
export type StressPerspectives = typeof StressPerspectivesSchema.Type
