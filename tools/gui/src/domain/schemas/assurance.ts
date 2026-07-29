import { Schema } from 'effect'

export const AssuranceNodeSchema = Schema.Struct({
  node_id: Schema.String,
  node_type: Schema.String,
  name: Schema.String,
  status: Schema.String,
  tlp: Schema.String,
  concern_class: Schema.NullOr(Schema.String),
  disposition: Schema.NullOr(Schema.String),
  uca_type: Schema.NullOr(Schema.String),
  binding_status: Schema.NullOr(Schema.String),
  node_role: Schema.NullOr(Schema.String),
  attributes_json: Schema.String,
  content_text: Schema.String,
  created_at: Schema.String,
  updated_at: Schema.String,
  created_by: Schema.String,
  analysis_id: Schema.NullOr(Schema.String),
})
export type AssuranceNode = typeof AssuranceNodeSchema.Type

export const AssuranceNodeListSchema = Schema.Struct({
  nodes: Schema.Array(AssuranceNodeSchema),
  count: Schema.Number,
  visibility_limited: Schema.Boolean,
})
export type AssuranceNodeList = typeof AssuranceNodeListSchema.Type
