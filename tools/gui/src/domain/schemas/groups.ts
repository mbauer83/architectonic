import { Schema } from 'effect'

export const GroupEntrySchema = Schema.Struct({
  slug: Schema.String,
  id: Schema.String,
  name: Schema.String,
  description: Schema.optional(Schema.String),
  order: Schema.optional(Schema.Number),
  archived: Schema.optional(Schema.Boolean),
  default: Schema.optional(Schema.Boolean),
  meta_ontology: Schema.optional(Schema.String),
  type_filter: Schema.optional(Schema.Array(Schema.String)),
  /** Whole-catalog member count per axis — sidebar badges must use this, never counts derived
   * from the currently loaded (group-filtered) list, which read zero for inactive groups. */
  member_count: Schema.optional(Schema.Number),
})
export type GroupEntry = typeof GroupEntrySchema.Type

export const GroupListSchema = Schema.Struct({
  'model-projects': Schema.optional(Schema.Array(GroupEntrySchema)),
  'diagram-collections': Schema.optional(Schema.Array(GroupEntrySchema)),
  'document-collections': Schema.optional(Schema.Array(GroupEntrySchema)),
  'analysis-collections': Schema.optional(Schema.Array(GroupEntrySchema)),
})
export type GroupList = typeof GroupListSchema.Type
