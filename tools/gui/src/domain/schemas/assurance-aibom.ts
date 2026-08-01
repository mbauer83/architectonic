import { Schema } from 'effect'

/**
 * Decoders for the AI-BOM surface.
 *
 * `AssuranceAibom.helpers.ts` coerced each of these field by field — `asStr`, `asNum`, `asStrList` —
 * which is what a client does when the server publishes no contract. It agreed with the routes, but
 * only by having been written carefully; nothing held the two together, and a coercion that silently
 * yields `''` for a missing name is indistinguishable from a component that has none.
 */
export const AiBomCandidateSchema = Schema.Struct({
  entity_id: Schema.String,
  name: Schema.String,
  entity_type: Schema.String,
  // A heuristic rank capped at 100, published with the reasons that produced it: a suggestion an
  // operator cannot interrogate is one they either take on faith or ignore.
  score: Schema.Number,
  reasons: Schema.Array(Schema.String),
})
export type AiBomCandidate = typeof AiBomCandidateSchema.Type

export const AiBomScanSchema = Schema.Struct({
  candidates: Schema.Array(AiBomCandidateSchema),
  count: Schema.Number,
  // Attached to the response, not to the docs: this is assistive output and the surface has to say so
  // where the operator is looking.
  note: Schema.String,
})

export const AiBomRolesSchema = Schema.Struct({
  roles: Schema.Array(Schema.String),
})

/** Two tiers, deliberately. A missing required attribute, dataset link or governance edge is
 *  blocking; a missing recommended attribute is advisory and never a validity blocker. Collapsed into
 *  one list, a wizard would demand information that is optional or genuinely unavailable. */
export const AiBomComponentCoverageSchema = Schema.Struct({
  entity_id: Schema.String,
  name: Schema.String,
  specialization: Schema.String,
  missing_required_attributes: Schema.Array(Schema.String),
  missing_recommended_attributes: Schema.Array(Schema.String),
  missing_dataset_linkage: Schema.Boolean,
  missing_governance: Schema.Boolean,
})
export type AiBomComponentCoverage = typeof AiBomComponentCoverageSchema.Type

export const AiBomCoverageSchema = Schema.Struct({
  components: Schema.Array(AiBomComponentCoverageSchema),
  unbound_roles: Schema.Array(Schema.String),
})
export type AiBomCoverage = typeof AiBomCoverageSchema.Type

/** `bom` stays unknown: it is a CycloneDX 1.6 document, and that specification's vocabulary is not
 *  this client's to restate — the panel serialises it for download rather than reading into it. */
export const AiBomExportSchema = Schema.Struct({
  bom: Schema.Record({ key: Schema.String, value: Schema.Unknown }),
  component_count: Schema.Number,
  coverage: AiBomCoverageSchema,
})
export type AiBomExport = typeof AiBomExportSchema.Type

export const decodeAiBomScan = (body: unknown): readonly AiBomCandidate[] =>
  Schema.decodeUnknownSync(AiBomScanSchema)(body).candidates

export const decodeAiBomCoverage = (body: unknown): AiBomCoverage =>
  Schema.decodeUnknownSync(AiBomCoverageSchema)(body)

export const decodeAiBomExport = (body: unknown): AiBomExport =>
  Schema.decodeUnknownSync(AiBomExportSchema)(body)
