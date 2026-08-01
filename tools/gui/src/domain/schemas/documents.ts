import { Schema } from 'effect'

// ── Frontmatter fields ────────────────────────────────────────────────────────

export const FrontmatterFieldSchema = Schema.Struct({
  name: Schema.String,
  field_type: Schema.String,
  // Absent, never null: the route omits unset optionals, so a scalar field simply has no element
  // type rather than having one that is null.
  array_items_type: Schema.optional(Schema.String),
  required: Schema.Boolean,
})
export type FrontmatterField = typeof FrontmatterFieldSchema.Type

// ── Document types ────────────────────────────────────────────────────────────

export const SectionSpecSchema = Schema.Struct({
  name: Schema.String,
  template: Schema.optional(Schema.String),
  required_entity_type_connections: Schema.optional(Schema.Array(Schema.String)),
  suggested_entity_type_connections: Schema.optional(Schema.Array(Schema.String)),
})
export type SectionSpec = typeof SectionSpecSchema.Type

export const DocumentTypeSchema = Schema.Struct({
  doc_type: Schema.String,
  abbreviation: Schema.String,
  name: Schema.String,
  subdirectory: Schema.String,
  required_sections: Schema.Array(Schema.String),
  // Not optional: the route fills each of these from the schema with a default, so every row carries
  // all nine keys. Declaring them optional described a response the server never sends and left every
  // reader writing a fallback for it.
  sections: Schema.Array(SectionSpecSchema),
  extra_frontmatter_fields: Schema.Array(FrontmatterFieldSchema),
  required_entity_type_connections: Schema.Array(Schema.String),
  suggested_entity_type_connections: Schema.Array(Schema.String),
})
export type DocumentType = typeof DocumentTypeSchema.Type

/** The envelope `GET /api/document-types` answers with; the adapter hands callers the list inside it. */
export const DocumentTypesSchema = Schema.Struct({
  document_types: Schema.Array(DocumentTypeSchema),
})

export const DocumentSummarySchema = Schema.Struct({
  artifact_id: Schema.String,
  doc_type: Schema.String,
  title: Schema.String,
  status: Schema.String,
  path: Schema.String,
  keywords: Schema.Array(Schema.String),
  sections: Schema.Array(Schema.String),
  group: Schema.optional(Schema.String),
  is_global: Schema.Boolean,
  last_updated: Schema.optional(Schema.NullOr(Schema.String)),
})
export type DocumentSummary = typeof DocumentSummarySchema.Type

export const DocumentListSchema = Schema.Struct({
  total: Schema.Number,
  items: Schema.Array(DocumentSummarySchema),
})
export type DocumentList = typeof DocumentListSchema.Type

/**
 * One document with its content, as the detail read serves it.
 *
 * The route reads in `full` mode unconditionally, so `content_text` and `extra` always arrive; the
 * handler always resolves `is_global` and the record always carries a `group`. All four were
 * optional here, which described a summary-mode answer this route cannot give.
 */
export const DocumentDetailSchema = Schema.Struct({
  artifact_id: Schema.String,
  artifact_type: Schema.Literal('document'),
  doc_type: Schema.String,
  title: Schema.String,
  status: Schema.String,
  record_type: Schema.Literal('document'),
  path: Schema.String,
  keywords: Schema.Array(Schema.String),
  sections: Schema.Array(Schema.String),
  group: Schema.String,
  content_snippet: Schema.String,
  content_text: Schema.String,
  is_global: Schema.Boolean,
  last_updated: Schema.optional(Schema.NullOr(Schema.String)),
  extra: Schema.Record({ key: Schema.String, value: Schema.Unknown }),
})
export type DocumentDetail = typeof DocumentDetailSchema.Type
