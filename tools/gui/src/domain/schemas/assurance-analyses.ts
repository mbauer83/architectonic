import { Schema } from 'effect'

/**
 * The methods and statuses an analysis may have, in one place on this side of the wire.
 *
 * They were spelled out again in `AssuranceAnalysisPicker.helpers.ts`, whose comment asked a test to
 * hold that copy equal to a tuple in a Python file. The vocabularies are published in the OpenAPI
 * document now, so the decoder below carries them and `openapi.contract.test-d.ts` compares them to
 * the document — a type error rather than a string comparison, and one copy rather than two.
 */
export const ANALYSIS_METHODS = ['STPA', 'CAST', 'GRC', 'FMEA'] as const
export type AnalysisMethod = (typeof ANALYSIS_METHODS)[number]

export const ANALYSIS_STATUSES = ['draft', 'active', 'completed', 'archived'] as const
export type AnalysisStatus = (typeof ANALYSIS_STATUSES)[number]

export const AssuranceAnalysisRecordSchema = Schema.Struct({
  analysis_id: Schema.String,
  // Filing, and null until someone files it — an answer rather than a missing key.
  group_id: Schema.NullOr(Schema.String),
  name: Schema.String,
  method: Schema.Literal(...ANALYSIS_METHODS),
  // Empty when the analysis spans several systems instead of naming one.
  architecture_anchor_id: Schema.String,
  status: Schema.Literal(...ANALYSIS_STATUSES),
  // Not a closed set: nothing validates it on the way in, so the server does not declare one.
  tlp: Schema.String,
  created_at: Schema.String,
  updated_at: Schema.String,
})
export type AssuranceAnalysisRecord = typeof AssuranceAnalysisRecordSchema.Type

/** The analyses this reader may see. `visibility_limited` says the view is partial, never by how much. */
export const AssuranceAnalysisListSchema = Schema.Struct({
  analyses: Schema.Array(AssuranceAnalysisRecordSchema),
  count: Schema.Number,
  visibility_limited: Schema.Boolean,
})
export type AssuranceAnalysisList = typeof AssuranceAnalysisListSchema.Type

/** One analysis with the size of its authored contents, exposure-filtered like everything here. */
export const AssuranceAnalysisDetailSchema = Schema.Struct({
  analysis: AssuranceAnalysisRecordSchema,
  node_count: Schema.Number,
})
export type AssuranceAnalysisDetail = typeof AssuranceAnalysisDetailSchema.Type

/** An analysis named just enough to show beside a node it authored — five fields, not the record. */
export const AssuranceAnalysisSummarySchema = Schema.Struct({
  analysis_id: Schema.String,
  name: Schema.String,
  method: Schema.Literal(...ANALYSIS_METHODS),
  status: Schema.Literal(...ANALYSIS_STATUSES),
  group_id: Schema.NullOr(Schema.String),
})
export type AssuranceAnalysisSummary = typeof AssuranceAnalysisSummarySchema.Type

/**
 * One node matched by a store-wide search.
 *
 * `path` is always empty and there is no snippet: a snippet may carry classified text, and an
 * assurance node has no file to point at — the field stays so one component renders architecture and
 * assurance hits alike. `analysis` is always sent and is null when the authoring analysis is above the
 * reader's ceiling, which is why it is `NullOr` and not `optional`: the edge picker's own interface had
 * it optional, and an absent key there would have read as "no analysis" rather than "not shown".
 */
export const AssuranceSearchHitSchema = Schema.Struct({
  score: Schema.Number,
  record_type: Schema.Literal('assurance-node'),
  artifact_id: Schema.String,
  name: Schema.String,
  artifact_type: Schema.String,
  status: Schema.String,
  path: Schema.String,
  analysis: Schema.NullOr(AssuranceAnalysisSummarySchema),
})
export type AssuranceSearchHit = typeof AssuranceSearchHitSchema.Type

export const AssuranceSearchSchema = Schema.Struct({
  query: Schema.String,
  hits: Schema.Array(AssuranceSearchHitSchema),
  count: Schema.Number,
})
export type AssuranceSearch = typeof AssuranceSearchSchema.Type

export const decodeSearchHits = (body: unknown): AssuranceSearchHit[] => [
  ...Schema.decodeUnknownSync(AssuranceSearchSchema)(body).hits,
]

/** A filing group. No classification of its own — the store's ceiling governs what is filed in it. */
export const AssuranceGroupRecordSchema = Schema.Struct({
  group_id: Schema.String,
  name: Schema.String,
  description: Schema.String,
  created_at: Schema.String,
  updated_at: Schema.String,
})
export type AssuranceGroupRecord = typeof AssuranceGroupRecordSchema.Type

export const AssuranceGroupListSchema = Schema.Struct({
  groups: Schema.Array(AssuranceGroupRecordSchema),
})
export type AssuranceGroupList = typeof AssuranceGroupListSchema.Type

/** Which participations an analysis holds — ids, because the working-set page serves the nodes. */
export const AssuranceParticipatingNodesSchema = Schema.Struct({
  analysis_id: Schema.String,
  participating_node_ids: Schema.Array(Schema.String),
  count: Schema.Number,
  visibility_limited: Schema.Boolean,
})
export type AssuranceParticipatingNodes = typeof AssuranceParticipatingNodesSchema.Type

/**
 * Decoders over the two collection bodies, so a caller reads a list rather than casting one.
 *
 * Here rather than beside each component: three surfaces read the analyses (the picker, the filing
 * tree, the browse view) and each had its own cast to its own looser interface. The array copy is
 * because effect decodes to a `ReadonlyArray` and the components hold their lists in a `ref`.
 */
export const decodeAnalysisList = (body: unknown): AssuranceAnalysisRecord[] => [
  ...Schema.decodeUnknownSync(AssuranceAnalysisListSchema)(body).analyses,
]

export const decodeGroupList = (body: unknown): AssuranceGroupRecord[] => [
  ...Schema.decodeUnknownSync(AssuranceGroupListSchema)(body).groups,
]

/**
 * The edge and reference vocabularies of the loaded assurance module.
 *
 * Edge types and reference types stay apart, and that is a module invariant rather than a
 * presentation choice: they are disjoint sets, and a reference type submitted as an edge type would
 * ask for a relation the graph rules do not define.
 *
 * `permitted` is grouped per (source, target) pair because that is the picker's actual question —
 * given these two ends, what may I draw — and a flat legality table would make the client re-derive
 * the grouping the module already knows.
 */
export const AssuranceEdgeTypeOptionSchema = Schema.Struct({
  name: Schema.String,
  label: Schema.String,
})

export const AssuranceEdgeTypePairSchema = Schema.Struct({
  source_type: Schema.String,
  target_type: Schema.String,
  connection_types: Schema.Array(Schema.String),
})
export type AssuranceEdgeTypePair = typeof AssuranceEdgeTypePairSchema.Type

export const AssuranceReferenceTypeOptionSchema = Schema.Struct({
  name: Schema.String,
  description: Schema.String,
})

export const AssuranceEdgeCatalogSchema = Schema.Struct({
  edge_types: Schema.Array(AssuranceEdgeTypeOptionSchema),
  permitted: Schema.Array(AssuranceEdgeTypePairSchema),
  reference_types: Schema.Array(AssuranceReferenceTypeOptionSchema),
})
export type AssuranceEdgeCatalog = typeof AssuranceEdgeCatalogSchema.Type

export const decodeEdgeCatalog = (body: unknown): AssuranceEdgeCatalog =>
  Schema.decodeUnknownSync(AssuranceEdgeCatalogSchema)(body)

/**
 * One completeness check, shared by every method's report and by the argument-completeness pass.
 *
 * The shape genuinely is one shape — `_check` is written identically in the STPA, GRC, CAST and GSN
 * report builders — so four decoders for it would be four things to keep in step.
 */
export const AssuranceCompletenessCheckSchema = Schema.Struct({
  passed: Schema.Boolean,
  gap_count: Schema.Number,
  gaps: Schema.Array(Schema.Struct({ node_id: Schema.String, name: Schema.String })),
})

export const AssuranceCompletenessReportSchema = Schema.Struct({
  passed: Schema.Boolean,
  // Keyed by check name, which is what a client renders. An open map with a closed value: the check
  // *set* belongs to the method's rules, not to this contract.
  checks: Schema.Record({ key: Schema.String, value: AssuranceCompletenessCheckSchema }),
  summary: Schema.String,
})

/**
 * The completeness report for one analysis, for the method the analysis itself declares.
 *
 * `baseline_count` and `incident_count` are CAST's alone — reproducibility requires a sealed baseline —
 * and are null for the other methods rather than zero: "not part of this method's report" and "none
 * found" are different claims, and `method` is what tells them apart.
 */
export const AssuranceAnalysisCompletenessSchema = Schema.Struct({
  analysis_id: Schema.String,
  method: Schema.Literal('STPA', 'CAST', 'GRC'),
  passed: Schema.Boolean,
  checks: Schema.Record({ key: Schema.String, value: AssuranceCompletenessCheckSchema }),
  summary: Schema.String,
  baseline_count: Schema.optional(Schema.NullOr(Schema.Number)),
  incident_count: Schema.optional(Schema.NullOr(Schema.Number)),
  case: AssuranceCompletenessReportSchema,
  visibility_limited: Schema.Boolean,
})
export type AssuranceAnalysisCompleteness = typeof AssuranceAnalysisCompletenessSchema.Type
