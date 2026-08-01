/**
 * Projection contracts: what a viewpoint shows, hides, and how it paints it.
 *
 * Split from `viewpoints.ts` to keep both within the module-size policy, the same seam
 * `viewpointTrace.ts` took — the two projection routes and the occurrence row they share are a
 * self-contained contract, and only the overlay surfaces consume them.
 *
 * The two routes are deliberately different shapes: `execute-projection` computes a projection and
 * stamps the generation it ran against, while a diagram may simply pin no viewpoint and answer
 * `{ applied: false }`.
 */
import { Schema } from 'effect'

/** A `mode: "scale"` style rule's per-item value: interpolate between `tokens` at
 * `position` (0..1) — never a discrete token, since the rule declares a continuous
 * spectrum rather than named bands. */
export const ScaleStyleValueSchema = Schema.Struct({
  position: Schema.Number,
  tokens: Schema.Tuple(Schema.String, Schema.String),
})
export type ScaleStyleValue = typeof ScaleStyleValueSchema.Type

export const StyleValueSchema = Schema.Union(Schema.String, ScaleStyleValueSchema)
export type StyleValue = typeof StyleValueSchema.Type

/** One projected item. `style` is empty whenever `reasons` is non-empty — an excluded
 * item is never styled, since a style token expresses semantics it does not satisfy.
 *
 * The connection fields are null on an entity and the entity fields null on a connection;
 * `item_kind` says which. They were absent here entirely, and an effect struct strips what
 * it does not declare, so a derived connection reached the overlay with its certainty, hop
 * count and witness ids removed. */
export const ProjectedOccurrenceSchema = Schema.Struct({
  item_id: Schema.String,
  item_kind: Schema.Literal('entity', 'connection'),
  state: Schema.Literal('visible', 'ghosted'),
  membership: Schema.Literal('primary', 'expanded'),
  reasons: Schema.Array(Schema.Literal('out_of_scope', 'criteria_mismatch', 'endpoint_excluded')),
  style: Schema.Record({ key: Schema.String, value: StyleValueSchema }),
  connection_type: Schema.NullOr(Schema.String),
  source_id: Schema.NullOr(Schema.String),
  target_id: Schema.NullOr(Schema.String),
  certainty: Schema.NullOr(Schema.Literal('certain', 'potential')),
  hops: Schema.NullOr(Schema.Number),
  via_connection_ids: Schema.Array(Schema.String),
  /** Entities only: the shortest witness chain a derived-evidence match rested on. */
  derived_match_hops: Schema.NullOr(Schema.Number),
  /** Entities only: one entry per authored column source, explicitly null where the
   * source does not resolve for this entity. */
  column_values: Schema.NullOr(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
})
export type ProjectedOccurrence = typeof ProjectedOccurrenceSchema.Type

export const ScaleLegendDataSchema = Schema.Struct({
  capability: Schema.String,
  attribute: Schema.String,
  minimum: Schema.Number,
  maximum: Schema.Number,
  tokens: Schema.Tuple(Schema.String, Schema.String),
})
export type ScaleLegendData = typeof ScaleLegendDataSchema.Type

/** One authored style rule's observable outcome for an execution — the "no silent
 * no-op" contract. `expected-empty` is a legitimate state rendered as a quiet badge;
 * `unresolvable` and `shadowed` also arrive as warnings. */
export const StyleRuleOutcomeSchema = Schema.Struct({
  rule_index: Schema.Number,
  capability: Schema.String,
  kind: Schema.Literal('applied', 'expected-empty', 'shadowed', 'unresolvable', 'disabled'),
  matched_count: Schema.Number,
  applied_count: Schema.Number,
  detail: Schema.NullOr(Schema.String),
})
export type StyleRuleOutcome = typeof StyleRuleOutcomeSchema.Type

/** The repository projection an execution computes. `applied` is always true — the
 * operation *produces* a projection, so there is no unprojected outcome — and every field
 * is present, which is why none of them is optional here. */
export const ViewpointProjectionSchema = Schema.Struct({
  applied: Schema.Literal(true),
  /** The model generation the styling ran against — the same provenance stamp `/execute`
   * carries, so a result and its styling can be shown to come from one snapshot. */
  index_generation: Schema.NullOr(Schema.Number),
  target: Schema.Literal('repository'),
  items: Schema.Array(ProjectedOccurrenceSchema),
  stale_pin: Schema.Boolean,
  warnings: Schema.Array(Schema.String),
  scale_legends: Schema.Array(ScaleLegendDataSchema),
  rule_outcomes: Schema.Array(StyleRuleOutcomeSchema),
})
export type ViewpointProjection = typeof ViewpointProjectionSchema.Type

/** A diagram that pins no viewpoint: the ordinary case, and the whole body. */
export const NoDiagramViewpointSchema = Schema.Struct({ applied: Schema.Literal(false) })

/** A diagram's saved projection. `stale_pin` is what this carries that the repository
 * projection cannot — the artifact pinned a version the definition has moved past. */
export const AppliedDiagramViewpointSchema = Schema.Struct({
  applied: Schema.Literal(true),
  target: Schema.Literal('diagram', 'matrix'),
  items: Schema.Array(ProjectedOccurrenceSchema),
  stale_pin: Schema.Boolean,
  warnings: Schema.Array(Schema.String),
  scale_legends: Schema.Array(ScaleLegendDataSchema),
  rule_outcomes: Schema.Array(StyleRuleOutcomeSchema),
})

export const DiagramViewpointProjectionSchema = Schema.Union(
  NoDiagramViewpointSchema,
  AppliedDiagramViewpointSchema,
)
export type DiagramViewpointProjection = typeof DiagramViewpointProjectionSchema.Type
