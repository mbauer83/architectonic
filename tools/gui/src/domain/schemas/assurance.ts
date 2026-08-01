import { Schema } from 'effect'

/**
 * One assurance node, as every backend now hands it back.
 *
 * This decoder was wrong in both directions at once. It required `created_by`, a SQLCipher column with
 * an empty default that nothing writes and nothing reads — so a deployment on any other store failed
 * the decode. And it omitted `failure_type` and `mode`, which every store writes, so an FMEA node's
 * own discriminators were invisible to a client that had decoded it successfully.
 *
 * `attributes_json` is a JSON *string*: the store keeps the column as text and passes it through, and
 * the wizards parse it a second time. Declaring it as an object here would be a schema the server does
 * not honour.
 */
export const AssuranceNodeSchema = Schema.Struct({
  node_id: Schema.String,
  node_type: Schema.String,
  name: Schema.String,
  status: Schema.String,
  tlp: Schema.String,
  concern_class: Schema.NullOr(Schema.String),
  disposition: Schema.NullOr(Schema.String),
  uca_type: Schema.NullOr(Schema.String),
  failure_type: Schema.NullOr(Schema.String),
  mode: Schema.NullOr(Schema.String),
  binding_status: Schema.NullOr(Schema.String),
  node_role: Schema.NullOr(Schema.String),
  attributes_json: Schema.String,
  content_text: Schema.String,
  created_at: Schema.String,
  updated_at: Schema.String,
  analysis_id: Schema.NullOr(Schema.String),
})
export type AssuranceNode = typeof AssuranceNodeSchema.Type

/** A node with how many visible edges reach it, either way. Both counts are always sent, including on
 *  an isolated node: zero and "not counted" are different facts. */
export const AssuranceNodeWithDegreesSchema = Schema.Struct({
  ...AssuranceNodeSchema.fields,
  conn_in: Schema.Number,
  conn_out: Schema.Number,
})
export type AssuranceNodeWithDegrees = typeof AssuranceNodeWithDegreesSchema.Type

export const AssuranceNodeListSchema = Schema.Struct({
  nodes: Schema.Array(AssuranceNodeWithDegreesSchema),
  count: Schema.Number,
  visibility_limited: Schema.Boolean,
})
export type AssuranceNodeList = typeof AssuranceNodeListSchema.Type

/** A node reached by a traversal, with how far out it was reached and whether it is the root. */
export const AssuranceNeighborhoodNodeSchema = Schema.Struct({
  ...AssuranceNodeSchema.fields,
  hop: Schema.Number,
  is_root: Schema.Boolean,
})
export type AssuranceNeighborhoodNode = typeof AssuranceNeighborhoodNodeSchema.Type

/** An edge crossed by a traversal. `direction` is relative to the node it was crossed from, which is
 *  why `self` is one of its values — a self-edge is neither incoming nor outgoing. */
export const AssuranceNeighborhoodEdgeSchema = Schema.Struct({
  edge_id: Schema.String,
  source_id: Schema.String,
  target_id: Schema.String,
  conn_type: Schema.String,
  attributes_json: Schema.String,
  created_at: Schema.String,
  source_name: Schema.String,
  source_type: Schema.String,
  target_name: Schema.String,
  target_type: Schema.String,
  hop: Schema.Number,
  direction: Schema.Literal('outgoing', 'incoming', 'self'),
})
export type AssuranceNeighborhoodEdge = typeof AssuranceNeighborhoodEdgeSchema.Type

/**
 * One node's neighbourhood, as far as the budgets and the reader's ceiling allow.
 *
 * `max_hops` is the budget that was applied after clamping, not what was asked for — the view had no
 * field for it at all, so a request for more hops than the deployment permits looked as though it had
 * been honoured.
 */
export const AssuranceNeighborhoodSchema = Schema.Struct({
  root_id: Schema.String,
  nodes: Schema.Array(AssuranceNeighborhoodNodeSchema),
  edges: Schema.Array(AssuranceNeighborhoodEdgeSchema),
  truncated: Schema.Boolean,
  frontier_node_ids: Schema.Array(Schema.String),
  max_hops: Schema.Number,
  visibility_limited: Schema.Boolean,
})
export type AssuranceNeighborhood = typeof AssuranceNeighborhoodSchema.Type
