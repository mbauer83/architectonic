/**
 * A viewpoint definition as the management view reads it: the authored record in canonical form,
 * plus what the server computed about it — tier, summaries, digest, fork staleness, broken
 * references.
 *
 * Split from `viewpoints.ts` to keep both within the module-size policy. The definition language
 * itself lives in `viewpointLanguage.ts`; this module is the envelope around it.
 */
import { Schema } from 'effect'

import { BrokenReferenceSchema } from './viewpointReferences'
import { PresentationSpecWireSchema, ViewpointQuerySpecSchema } from './viewpointLanguage'

/** The scope in words, for a list row that has no space for the scope itself. */
export const ScopeSummarySchema = Schema.Struct({
  unrestricted: Schema.Boolean,
  entity_types: Schema.optional(Schema.Array(Schema.String)),
  connection_types: Schema.optional(Schema.Array(Schema.String)),
  excluded_entity_types: Schema.optional(Schema.Array(Schema.String)),
  excluded_domains: Schema.optional(Schema.Array(Schema.String)),
  excluded_connection_types: Schema.optional(Schema.Array(Schema.String)),
})
export type ScopeSummary = typeof ScopeSummarySchema.Type

export const ConceptScopeSpecSchema = Schema.Struct({
  /** Absent means unrestricted, not "none": an empty list would select nothing. */
  entity_types: Schema.optional(Schema.Array(Schema.String)),
  connection_types: Schema.optional(Schema.Array(Schema.String)),
  excluded_entity_types: Schema.optional(Schema.Array(Schema.String)),
  excluded_domains: Schema.optional(Schema.Array(Schema.String)),
  excluded_connection_types: Schema.optional(Schema.Array(Schema.String)),
})

export const ForkLineageSpecSchema = Schema.Struct({
  slug: Schema.String,
  version: Schema.Number,
  definition_digest: Schema.String,
  index_generation: Schema.optional(Schema.Number),
})

export const ViewpointDefinitionEnvelopeSchema = Schema.Struct({
  slug: Schema.String,
  version: Schema.Number,
  name: Schema.String,
  description: Schema.optional(Schema.String),
  rationale: Schema.optional(Schema.String),
  /** A bare string for a single value and a list for several — the canonical shorthand,
   * kept so a hand-edited catalogue file round-trips unchanged. */
  purpose: Schema.Union(Schema.String, Schema.Array(Schema.String)),
  content: Schema.Union(Schema.String, Schema.Array(Schema.String)),
  stakeholders: Schema.optional(Schema.Array(Schema.String)),
  concerns: Schema.optional(Schema.Array(Schema.String)),
  scope: Schema.optional(ConceptScopeSpecSchema),
  representation_types: Schema.optional(Schema.Array(Schema.String)),
  derivation_defaults: Schema.optional(Schema.Record({
    key: Schema.String,
    value: Schema.Union(Schema.Number, Schema.Boolean, Schema.String),
  })),
  query: Schema.optional(ViewpointQuerySpecSchema),
  presentation: Schema.optional(PresentationSpecWireSchema),
  // Which selection layer is ACTIVE (scope | query); absent on pre-migration definitions,
  // where the legacy behavior (query when present, else scope) applies.
  selection_mode: Schema.optional(Schema.Literal('scope', 'query')),
  /** Fork provenance, stamped server-side at fork time (origin slug/version/content
   * digest); absent on non-forks. */
  forked_from: Schema.optional(ForkLineageSpecSchema),
  /** Digest-computed staleness against the CURRENT origin — 'stale' the moment the origin's
   * content changes, even without a version bump. Absent for a definition that is not a fork. */
  fork_status: Schema.optional(Schema.Literal('current', 'stale', 'origin-missing')),
  // The definition's CURRENT canonical content digest — verified execution references pin
  // it so a later open can say the definition changed.
  definition_digest: Schema.String,
  tier: Schema.Literal('module', 'enterprise', 'engagement'),
  scope_summary: ScopeSummarySchema,
  /** Absent for a scope-mode definition with no active query: there is no query to
   * summarise, which is not the same as a query that summarises to nothing. */
  query_summary: Schema.optional(Schema.String),
  /** Broken references, computed on demand and never persisted. */
  broken_references: Schema.Array(BrokenReferenceSchema),
})
export type ViewpointDefinitionEnvelope = typeof ViewpointDefinitionEnvelopeSchema.Type

export const ViewpointDefinitionListSchema = Schema.Struct({
  viewpoints: Schema.Array(ViewpointDefinitionEnvelopeSchema),
})

export type ConceptScopeSpec = typeof ConceptScopeSpecSchema.Type
export type ForkLineageSpec = typeof ForkLineageSpecSchema.Type
