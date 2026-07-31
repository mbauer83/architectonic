import { Schema } from 'effect'

/**
 * Decoders for the assurance analysis aggregate.
 *
 * The picker and the filing tree each described an analysis with their own hand-written interface and
 * a cast over `resp.json()`, and both declared `status`, `tlp` and `architecture_anchor_id` optional
 * for a route that has always sent them — a decoder more permissive than the server, which is the
 * direction that hides a real absence rather than reporting it.
 *
 * `method` and `status` are the closed vocabularies the backend now publishes. A method the domain
 * retires stops type-checking here, which is the check the duplicated `ANALYSIS_METHODS` list in
 * `AssuranceAnalysisPicker.helpers.ts` was standing in for.
 */
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
