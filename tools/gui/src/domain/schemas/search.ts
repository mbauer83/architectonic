import { Schema } from 'effect'

export const SearchHitSchema = Schema.Struct({
  score: Schema.Number,
  record_type: Schema.Union(
    Schema.Literal('entity'),
    Schema.Literal('connection'),
    Schema.Literal('diagram'),
    Schema.Literal('document'),
    Schema.Literal('assurance-node'),   // placeholder; consumed in WU-G3
    Schema.Literal('assurance-edge'),   // placeholder; consumed in WU-G3
  ),
  artifact_id: Schema.String,
  name: Schema.String,
  artifact_type: Schema.optional(Schema.String),
  status: Schema.String,
  path: Schema.String,
  source: Schema.optional(Schema.String),
  target: Schema.optional(Schema.String),
  is_global: Schema.optional(Schema.Boolean),
  domain: Schema.optional(Schema.String),
  subdomain: Schema.optional(Schema.String),
  diagram_type: Schema.optional(Schema.String),
})
export type SearchHit = typeof SearchHitSchema.Type

export const SearchResultSchema = Schema.Struct({
  query: Schema.String,
  hits: Schema.Array(SearchHitSchema),
})
export type SearchResult = typeof SearchResultSchema.Type

// ── Artifact search (cross-type) — unified with SearchHitSchema ───────────────

export const ArtifactSearchHitSchema = SearchHitSchema
export type ArtifactSearchHit = SearchHit

export const ArtifactSearchResultSchema = SearchResultSchema
export type ArtifactSearchResult = SearchResult

// ── Reference search ─────────────────────────────────────────────────────────

export const ReferenceSearchHitSchema = Schema.Struct({
  artifact_id: Schema.String,
  record_type: Schema.Union(
    Schema.Literal('entity'),
    Schema.Literal('diagram'),
    Schema.Literal('document'),
  ),
  name: Schema.String,
  status: Schema.String,
  path: Schema.String,
  domain: Schema.optional(Schema.NullOr(Schema.String)),
  artifact_type: Schema.optional(Schema.String),
  diagram_type: Schema.optional(Schema.String),
  doc_type: Schema.optional(Schema.String),
  sections: Schema.optional(Schema.Array(Schema.String)),
  is_global: Schema.optional(Schema.Boolean),
})
export type ReferenceSearchHit = typeof ReferenceSearchHitSchema.Type

export const ReferenceSearchResultSchema = Schema.Struct({
  query: Schema.String,
  hits: Schema.Array(ReferenceSearchHitSchema),
})
export type ReferenceSearchResult = typeof ReferenceSearchResultSchema.Type
