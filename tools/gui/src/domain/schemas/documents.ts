import { Schema } from 'effect'

// ── Frontmatter fields ────────────────────────────────────────────────────────

export const FrontmatterFieldSchema = Schema.Struct({
  name: Schema.String,
  field_type: Schema.String,
  array_items_type: Schema.optional(Schema.NullOr(Schema.String)),
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
  sections: Schema.optional(Schema.Array(SectionSpecSchema)),
  extra_frontmatter_fields: Schema.optional(Schema.Array(FrontmatterFieldSchema)),
  required_entity_type_connections: Schema.optional(Schema.Array(Schema.String)),
  suggested_entity_type_connections: Schema.optional(Schema.Array(Schema.String)),
})
export type DocumentType = typeof DocumentTypeSchema.Type

export const DocumentTypesSchema = Schema.Array(DocumentTypeSchema)

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
  content_snippet: Schema.String,
  content_text: Schema.optional(Schema.String),
  is_global: Schema.optional(Schema.Boolean),
  extra: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
})
export type DocumentDetail = typeof DocumentDetailSchema.Type
