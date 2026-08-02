import { Schema } from 'effect'

export const ServerInfoSchema = Schema.Struct({
  admin_mode: Schema.Boolean,
  read_only: Schema.Boolean,
  engagement_root: Schema.NullOr(Schema.String),
  enterprise_root: Schema.NullOr(Schema.String),
})
export type ServerInfo = typeof ServerInfoSchema.Type

export const ModuleSummarySchema = Schema.Struct({
  name: Schema.String,
  module_class: Schema.String,
  enabled: Schema.Boolean,
  requires: Schema.Array(Schema.String),
  entity_type_count: Schema.Number,
  connection_type_count: Schema.Number,
})
export type ModuleSummary = typeof ModuleSummarySchema.Type

/** The envelope `GET /api/modules` answers with; the adapter hands callers the list inside it. */
export const ModuleSummaryListSchema = Schema.Struct({
  modules: Schema.Array(ModuleSummarySchema),
})

export const WriteHelpEntityTypeCatalogEntrySchema = Schema.Struct({
  prefix: Schema.String,
})
export type WriteHelpEntityTypeCatalogEntry =
  typeof WriteHelpEntityTypeCatalogEntrySchema.Type

/**
 * The slice of `/api/write-help` this client reads.
 *
 * The response declares ten fields; two are used here, and one of those only for its `prefix`. A
 * decoder narrower than its document is not drift — `Schema.Struct` ignores excess keys — but it
 * cannot be asserted with plain equality either, which is how it sat in `UNASSERTED_SCHEMAS` as
 * "not yet compared" and hid the one real divergence: `entity_type_catalog` is required in the
 * document and the server has no default for it, so the `optional` here was the client permitting
 * an absence the producer cannot express. The contract test asserts this against a named projection
 * of the document, so drift in the fields it *does* read still fails.
 */
export const WriteHelpSchema = Schema.Struct({
  entity_types_by_domain: Schema.Record({
    key: Schema.String,
    value: Schema.Array(Schema.String),
  }),
  entity_type_catalog: Schema.Record({
    key: Schema.String,
    value: WriteHelpEntityTypeCatalogEntrySchema,
  }),
})
export type WriteHelp = typeof WriteHelpSchema.Type
