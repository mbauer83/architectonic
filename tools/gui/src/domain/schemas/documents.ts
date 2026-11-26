import { Schema } from 'effect'
import { BaselineStandingSchema } from './baselineStanding'

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

/**
 * One column of a typed table a section declares.
 *
 * Open, mirroring the server's `DocumentTableColumn`: a value column is written as a property of an
 * attribute schema is, so `enum`, `pattern`, `minimum` and the other JSON Schema keywords arrive
 * through the index signature, and the column with its `type` is the schema of one cell.
 */
export const TableColumnSchema = Schema.Struct(
  {
    name: Schema.String,
    title: Schema.String,
    required: Schema.Boolean,
    type: Schema.String,
    to: Schema.optional(Schema.Array(Schema.String)),
    table: Schema.optional(Schema.String),
    kind: Schema.optional(Schema.String),
    words: Schema.optional(Schema.Array(Schema.String)),
    many: Schema.optional(Schema.Boolean),
  },
  Schema.Record({ key: Schema.String, value: Schema.Unknown }),
)
export type TableColumn = typeof TableColumnSchema.Type

export const TableDeclarationSchema = Schema.Struct({
  name: Schema.String,
  row_id: Schema.String,
  row_id_title: Schema.String,
  columns: Schema.Array(TableColumnSchema),
})
export type TableDeclaration = typeof TableDeclarationSchema.Type

export const SectionSpecSchema = Schema.Struct({
  name: Schema.String,
  template: Schema.optional(Schema.String),
  required_connections: Schema.optional(Schema.Array(Schema.String)),
  suggested_connections: Schema.optional(Schema.Array(Schema.String)),
  tables: Schema.optional(Schema.Array(TableDeclarationSchema)),
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
  required_connections: Schema.Array(Schema.String),
  suggested_connections: Schema.Array(Schema.String),
  /**
   * Present only for a type reproducing a third-party template; the create form shows it.
   *
   * Optional rather than nullable, like every other unset field on this surface: the route sends
   * `response_model_exclude_none`, so an absent attribution is absent rather than null.
   */
  attribution: Schema.optional(Schema.String),
})
export type DocumentType = typeof DocumentTypeSchema.Type

/** The envelope `GET /api/document-types` answers with; the adapter hands callers the list inside it. */
export const DocumentTypesSchema = Schema.Struct({
  document_types: Schema.Array(DocumentTypeSchema),
})

/** The first name a new document of a type may take (`GET /api/document-types/{type}/free-title`). */
export const FreeDocumentTitleSchema = Schema.Struct({
  doc_type: Schema.String,
  asked: Schema.String,
  title: Schema.String,
})
export type FreeDocumentTitle = typeof FreeDocumentTitleSchema.Type

export const DocumentSummarySchema = Schema.Struct({
  artifact_id: Schema.String,
  doc_type: Schema.String,
  title: Schema.String,
  status: Schema.String,
  path: Schema.String,
  keywords: Schema.Array(Schema.String),
  sections: Schema.Array(Schema.String),
  // Required, not optional. `DocumentSummary.group` has no default, so the route would 500 rather
  // than omit it — the client was the permissive side, and a decoder wider than its producer hides
  // the day the producer stops filling the field.
  group: Schema.String,
  is_global: Schema.Boolean,
  baseline_standing: BaselineStandingSchema,
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
  baseline_standing: BaselineStandingSchema,
  last_updated: Schema.optional(Schema.NullOr(Schema.String)),
  extra: Schema.Record({ key: Schema.String, value: Schema.Unknown }),
})
export type DocumentDetail = typeof DocumentDetailSchema.Type
