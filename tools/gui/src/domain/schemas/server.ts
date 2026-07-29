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

export const ModuleSummaryListSchema = Schema.Array(ModuleSummarySchema)

export const WriteHelpEntityTypeCatalogEntrySchema = Schema.Struct({
  prefix: Schema.String,
})
export type WriteHelpEntityTypeCatalogEntry =
  typeof WriteHelpEntityTypeCatalogEntrySchema.Type

export const WriteHelpSchema = Schema.Struct({
  entity_types_by_domain: Schema.Record({
    key: Schema.String,
    value: Schema.Array(Schema.String),
  }),
  entity_type_catalog: Schema.optional(
    Schema.Record({
      key: Schema.String,
      value: WriteHelpEntityTypeCatalogEntrySchema,
    }),
  ),
})
export type WriteHelp = typeof WriteHelpSchema.Type
