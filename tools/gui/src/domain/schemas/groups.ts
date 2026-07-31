import { Schema } from 'effect'

export const GroupEntrySchema = Schema.Struct({
  slug: Schema.String,
  id: Schema.String,
  name: Schema.String,
  // None of these is optional: the domain's `GroupEntry` gives each a default and the route emits all
  // ten keys, so a reader's fallback was for a response that never arrives.
  description: Schema.String,
  order: Schema.Number,
  archived: Schema.Boolean,
  default: Schema.Boolean,
  meta_ontology: Schema.String,
  type_filter: Schema.Array(Schema.String),
  /** Whole-catalog member count per axis — sidebar badges must use this, never counts derived
   * from the currently loaded (group-filtered) list, which read zero for inactive groups. */
  member_count: Schema.Number,
})
export type GroupEntry = typeof GroupEntrySchema.Type

export const GroupListSchema = Schema.Struct({
  'model-projects': Schema.optional(Schema.Array(GroupEntrySchema)),
  'diagram-collections': Schema.optional(Schema.Array(GroupEntrySchema)),
  'document-collections': Schema.optional(Schema.Array(GroupEntrySchema)),
  'analysis-collections': Schema.optional(Schema.Array(GroupEntrySchema)),
})
export type GroupList = typeof GroupListSchema.Type
