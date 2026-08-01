import { Schema } from 'effect'

/**
 * One artifact matched by keyword, with the display fields its kind actually has.
 *
 * `name` and `artifact_type` are the *display* reading: a document's title arrives as `name` and its
 * doc type as `artifact_type`, because a mixed result list has one column for each.
 *
 * `last_updated` was declared nowhere here while the route sent it on every hit — the direction of
 * drift a decoder cannot report, because a field it does not know about simply never appears. The two
 * assurance literals went the other way: they were placeholders for a consumption that happened at a
 * different address, and this route cannot return them.
 */
export const SearchHitSchema = Schema.Struct({
  score: Schema.Number,
  record_type: Schema.Literal('entity', 'connection', 'diagram', 'document'),
  artifact_id: Schema.String,
  status: Schema.String,
  path: Schema.String,
  last_updated: Schema.NullOr(Schema.String),
  name: Schema.String,
  artifact_type: Schema.String,
  // Each filled by exactly one kind: domain/subdomain by an entity, diagram_type by a diagram,
  // source/target by a connection.
  domain: Schema.optional(Schema.NullOr(Schema.String)),
  subdomain: Schema.optional(Schema.NullOr(Schema.String)),
  is_global: Schema.optional(Schema.NullOr(Schema.Boolean)),
  // Present together, only for a construct a diagram owns — how a display surface tells one from a
  // model entity.
  host_diagram_id: Schema.optional(Schema.NullOr(Schema.String)),
  diagram_internal: Schema.optional(Schema.NullOr(Schema.Boolean)),
  diagram_type: Schema.optional(Schema.NullOr(Schema.String)),
  source: Schema.optional(Schema.NullOr(Schema.String)),
  target: Schema.optional(Schema.NullOr(Schema.String)),
})
export type SearchHit = typeof SearchHitSchema.Type

export const SearchResultSchema = Schema.Struct({
  query: Schema.String,
  hits: Schema.Array(SearchHitSchema),
})
export type SearchResult = typeof SearchResultSchema.Type

// ── Artifact search (cross-type) — a *different* search, not the same one ─────
//
// These were aliases of the keyword schemas. The display search projects six fields for a picker
// rather than serialising a whole record, and it reaches the assurance store too — so it can return
// `assurance-node`, which the keyword search never does, and omits the domain and endpoint fields the
// alias promised.

export const ArtifactSearchHitSchema = Schema.Struct({
  score: Schema.Number,
  record_type: Schema.Literal('entity', 'connection', 'diagram', 'document', 'assurance-node'),
  artifact_id: Schema.String,
  name: Schema.String,
  status: Schema.String,
  // Empty for an assurance node: it has no file.
  path: Schema.String,
  // Filled only for an assurance node, whose kind is what tells a hazard from a loss in a mixed list.
  artifact_type: Schema.optional(Schema.NullOr(Schema.String)),
})
export type ArtifactSearchHit = typeof ArtifactSearchHitSchema.Type

export const ArtifactSearchResultSchema = Schema.Struct({
  query: Schema.String,
  hits: Schema.Array(ArtifactSearchHitSchema),
})
export type ArtifactSearchResult = typeof ArtifactSearchResultSchema.Type

// ── Reference search ─────────────────────────────────────────────────────────

/** No `score`: this filters rather than ranks, so every hit is equally a match. */
export const ReferenceSearchHitSchema = Schema.Struct({
  artifact_id: Schema.String,
  record_type: Schema.Literal('entity', 'diagram', 'document'),
  name: Schema.String,
  status: Schema.String,
  path: Schema.String,
  // An entity's own domain or a diagram's inferred one, and absent for a document — a document is
  // filed by type rather than by domain.
  domain: Schema.optional(Schema.NullOr(Schema.String)),
  artifact_type: Schema.optional(Schema.NullOr(Schema.String)),
  diagram_type: Schema.optional(Schema.NullOr(Schema.String)),
  doc_type: Schema.optional(Schema.NullOr(Schema.String)),
  // A document's alone: a citation may target a section, and offering the list is what makes that
  // possible without a second request.
  sections: Schema.optional(Schema.NullOr(Schema.Array(Schema.String))),
  is_global: Schema.optional(Schema.NullOr(Schema.Boolean)),
})
export type ReferenceSearchHit = typeof ReferenceSearchHitSchema.Type

export const ReferenceSearchResultSchema = Schema.Struct({
  query: Schema.String,
  hits: Schema.Array(ReferenceSearchHitSchema),
})
export type ReferenceSearchResult = typeof ReferenceSearchResultSchema.Type
