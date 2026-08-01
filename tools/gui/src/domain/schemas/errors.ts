import { Schema } from 'effect'

/**
 * The backend's error envelope, decoded.
 *
 * Every error response on the REST surface has this shape: `detail` is an object, not a sentence.
 * Decoding it is what lets a caller branch on `code` instead of matching on prose, and surface
 * `request_id` to a user who needs to report something.
 *
 * `details` is a closed union keyed by the code, mirroring the server's per-code DTOs. Decoding it
 * as an open object would have been less work and would have thrown away the reason it exists: a
 * caller that cannot narrow `details` is back to reading the message.
 *
 * The type-level contract assertions in `openapi.contract.test-d.ts` hold these against the
 * generated OpenAPI types, so a code added on the server without a decoder here is a type error.
 */

export const ERROR_CODES = [
  'bad_request',
  'forbidden',
  'not_found',
  'conflict',
  'validation_error',
  'write_rejected',
  'internal_error',
  'assurance_store_locked',
  'signal_mutation_denied',
  'invalid_vex_assessment',
  'analysis_method_mismatch',
  'analysis_not_empty',
  'entity_in_use',
  'provenance_immutable',
  'provenance_required',
  'invalid_participation',
  'node_legacy_invalid',
  // Assurance graph shape — each carries data the caller acts on differently.
  'duplicate_edge',
  'illegal_connection_type',
  'not_a_failure_mode',
  'traversal_time_budget_exceeded',
  'unknown_diagram_type',
  // Same reasoning, one surface over: the guidance catalogue is fixed, so an unknown topic names no
  // resource, and the reply is worth more as the topics that do exist than as prose.
  'unknown_guidance_topic',
  // A GSN diagram leaves the confidential store, so publishing one is refused when the argument's own
  // effective classification forbids it. It carries that classification: prose cannot be ranked.
  'classification_not_publishable',
  // The deployment lacks a capability: nothing the caller sends will fix it.
  'not_configured',
  'viewpoint_referenced',
] as const

export const ErrorCodeSchema = Schema.Literal(...ERROR_CODES)
export type ErrorCode = typeof ErrorCodeSchema.Type

export const FieldErrorSchema = Schema.Struct({
  field: Schema.String,
  message: Schema.String,
})

export const ValidationErrorDetailsSchema = Schema.Struct({
  field_errors: Schema.Array(FieldErrorSchema),
})

/** A denial the caller may or may not be able to retry. `retryable` is a decision, not a guess. */
export const DenialDetailsSchema = Schema.Struct({
  reason_code: Schema.String,
  // Required, not optional: the field has a server-side default, so it is *always* serialized.
  // Declaring it optional would let a caller treat "absent" as a fourth state that never occurs.
  retryable: Schema.Boolean,
})

export const MethodMismatchDetailsSchema = Schema.Struct({
  analysis_id: Schema.String,
  expected_method: Schema.String,
  actual_method: Schema.String,
})

export const AnalysisNotEmptyDetailsSchema = Schema.Struct({
  analysis_id: Schema.String,
  authored_node_count: Schema.Number,
})

export const EntityInUseDetailsSchema = Schema.Struct({
  node_id: Schema.String,
  referencing_analysis_ids: Schema.Array(Schema.String),
})

export const ProvenanceImmutableDetailsSchema = Schema.Struct({
  node_id: Schema.String,
  current_analysis_id: Schema.String,
})

export const InvalidParticipationDetailsSchema = Schema.Struct({
  node_id: Schema.String,
  analysis_id: Schema.String,
})

export const LegacyInvalidDetailsSchema = Schema.Struct({
  node_id: Schema.String,
  permitted_operation: Schema.String,
})

export const DuplicateEdgeDetailsSchema = Schema.Struct({
  edge_id: Schema.String,
  source_id: Schema.String,
  target_id: Schema.String,
  conn_type: Schema.String,
})

export const IllegalConnectionTypeDetailsSchema = Schema.Struct({
  source_type: Schema.String,
  target_type: Schema.String,
  conn_type: Schema.String,
  legal_types: Schema.Array(Schema.String),
})

export const NotAFailureModeDetailsSchema = Schema.Struct({
  node_id: Schema.String,
})

export const UnknownDiagramTypeDetailsSchema = Schema.Struct({
  diagram_type: Schema.String,
  analysis_id: Schema.String,
  method: Schema.String,
  available: Schema.Array(Schema.String),
})

export const UnknownGuidanceTopicDetailsSchema = Schema.Struct({
  topic: Schema.String,
  available_topics: Schema.Array(Schema.String),
})

export const ClassificationNotPublishableDetailsSchema = Schema.Struct({
  effective_tlp: Schema.String,
})

export const NotConfiguredDetailsSchema = Schema.Struct({
  capability: Schema.String,
  remedy: Schema.String,
})

export const ViewpointReferencerRefSchema = Schema.Struct({
  artifact_id: Schema.String,
  target_kind: Schema.Literal('diagram', 'matrix'),
})

export const ViewpointReferencedDetailsSchema = Schema.Struct({
  slug: Schema.String,
  referencers: Schema.Array(ViewpointReferencerRefSchema),
})

export const ErrorDetailsSchema = Schema.Union(
  ValidationErrorDetailsSchema,
  DenialDetailsSchema,
  MethodMismatchDetailsSchema,
  AnalysisNotEmptyDetailsSchema,
  EntityInUseDetailsSchema,
  ProvenanceImmutableDetailsSchema,
  InvalidParticipationDetailsSchema,
  LegacyInvalidDetailsSchema,
  DuplicateEdgeDetailsSchema,
  IllegalConnectionTypeDetailsSchema,
  NotAFailureModeDetailsSchema,
  UnknownDiagramTypeDetailsSchema,
  UnknownGuidanceTopicDetailsSchema,
  ClassificationNotPublishableDetailsSchema,
  NotConfiguredDetailsSchema,
  ViewpointReferencedDetailsSchema,
)

export const ErrorBodySchema = Schema.Struct({
  code: ErrorCodeSchema,
  details: Schema.optional(Schema.NullOr(ErrorDetailsSchema)),
  message: Schema.String,
  request_id: Schema.String,
})

export const ErrorEnvelopeSchema = Schema.Struct({
  detail: ErrorBodySchema,
})

export type ErrorEnvelope = typeof ErrorEnvelopeSchema.Type
export type ErrorBody = typeof ErrorBodySchema.Type
export type ErrorDetails = typeof ErrorDetailsSchema.Type

/** Whether a failure is worth offering the user a retry for. */
export const isRetryable = (body: ErrorBody): boolean =>
  body.details != null && 'retryable' in body.details && body.details.retryable === true

export type ViewpointReferencedDetails = typeof ViewpointReferencedDetailsSchema.Type

/**
 * The referencers a `viewpoint_referenced` refusal carries, or null for any other failure.
 *
 * The union is not discriminated by `code` on the wire — the server keys details off the code, but
 * the envelope nests them — so narrowing needs both the code and a shape check. Doing it here means
 * no component re-derives the narrowing and gets it subtly wrong.
 */
export const viewpointReferencedDetails = (body: ErrorBody): ViewpointReferencedDetails | null =>
  body.code === 'viewpoint_referenced' && body.details != null && 'referencers' in body.details
    ? body.details
    : null
