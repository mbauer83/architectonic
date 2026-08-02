/**
 * The viewpoint definition language on the wire: criteria trees, queries and presentations, in the
 * canonical form the catalogue file holds and a save accepts back.
 *
 * These used to be `Schema.Unknown` on the envelope, on the grounds that the recursive shape was
 * modelled by the plain TS types in `../viewpointCriteria.ts`. Those types are the *builder* model —
 * camelCase, id-bearing, editable — and they are not this. Leaving the wire side untyped meant the
 * one payload the editor round-trips whole had no contract at either end, so nothing could tell
 * whether the two agreed.
 *
 * Recursive schemas use `Schema.suspend`, which is what lets a group hold groups. Every optional is
 * `Schema.optional`, never `NullOr`: the canonical form omits defaults, and a null would make a
 * re-save write a key the parser reads as a value.
 */
import { Schema } from 'effect'

export const ParameterValueRefSchema = Schema.Struct({
  from: Schema.Literal('parameter'),
  name: Schema.String,
})

export const BindingValueRefSchema = Schema.Struct({
  from: Schema.Literal('binding'),
  name: Schema.String,
  project: Schema.optional(Schema.String),
  aggregate: Schema.optional(Schema.Literal('count', 'sum', 'avg', 'min', 'max')),
  /** What a set-valued binding means in a scalar comparison: `any` member, or `all` of them. */
  quantifier: Schema.optional(Schema.Literal('any', 'all')),
})

export const AttributeValueRefSchema = Schema.Struct({
  /** `self` reads the record being evaluated; `source`/`target` read an endpoint of the
   * connection being evaluated, and mean nothing outside one. */
  from: Schema.Literal('self', 'source', 'target'),
  attribute: Schema.String,
})

export const ValueRefSchema = Schema.Union(
  ParameterValueRefSchema,
  BindingValueRefSchema,
  AttributeValueRefSchema,
)

/** A condition's comparison value: one of the references, or a literal — a scalar for the
 * ordinary operators and a list for the membership ones. */
export const ConditionValueSchema = Schema.Union(
  ValueRefSchema,
  Schema.String,
  Schema.Number,
  Schema.Boolean,
  Schema.Array(Schema.Union(Schema.String, Schema.Number, Schema.Boolean)),
)

export const ComparatorSchema = Schema.Literal(
  'eq', 'neq', 'in', 'not_in', 'exists', 'absent', 'lt', 'lte', 'gt', 'gte', 'like', 'ilike',
)

/** `negate` is a strict logical complement, a missing attribute included — a negated `eq` matches
 * a record with no such attribute at all, which `neq` deliberately does not. */
export const AttributeConditionNodeSchema = Schema.Struct({
  kind: Schema.Literal('condition'),
  attribute: Schema.String,
  comparator: ComparatorSchema,
  value: Schema.optional(ConditionValueSchema),
  negate: Schema.optional(Schema.Boolean),
})
export type AttributeConditionNode = typeof AttributeConditionNodeSchema.Type

export interface EntityCriteriaGroupNode {
  readonly kind: 'group'
  readonly conjunction: 'and' | 'or'
  readonly children: ReadonlyArray<EntityCriteriaNode>
  readonly negate?: boolean
}

export interface ConnectionCriteriaGroupNode {
  readonly kind: 'group'
  readonly conjunction: 'and' | 'or'
  readonly children: ReadonlyArray<ConnectionCriteriaNode>
  readonly negate?: boolean
}

/** "This entity has an incident connection matching `connection_criteria` whose other endpoint
 * matches `endpoint_criteria`" — recursive on both legs. `traversal` is always written, even at its
 * default: it is load-bearing semantics, and `both` is the union of the direct and derived sets
 * taken *before* negation. */
export interface IncidentConnectionNode {
  readonly kind: 'incident'
  readonly traversal: 'direct' | 'derived' | 'both'
  readonly direction?: 'outgoing' | 'incoming' | 'either'
  readonly connection_criteria?: ConnectionCriteriaGroupNode
  readonly endpoint_criteria?: EntityCriteriaGroupNode
  readonly negate?: boolean
  readonly include_potential?: boolean
  readonly max_hops?: number
}

export type EntityCriteriaNode = AttributeConditionNode | IncidentConnectionNode | EntityCriteriaGroupNode
export type ConnectionCriteriaNode = AttributeConditionNode | ConnectionCriteriaGroupNode

export const ConnectionCriteriaGroupNodeSchema: Schema.Schema<ConnectionCriteriaGroupNode> = Schema.Struct({
  kind: Schema.Literal('group'),
  conjunction: Schema.Literal('and', 'or'),
  children: Schema.Array(
    Schema.Union(
      AttributeConditionNodeSchema,
      Schema.suspend((): Schema.Schema<ConnectionCriteriaGroupNode> => ConnectionCriteriaGroupNodeSchema),
    ),
  ),
  negate: Schema.optional(Schema.Boolean),
})

export const IncidentConnectionNodeSchema: Schema.Schema<IncidentConnectionNode> = Schema.Struct({
  kind: Schema.Literal('incident'),
  traversal: Schema.Literal('direct', 'derived', 'both'),
  direction: Schema.optional(Schema.Literal('outgoing', 'incoming', 'either')),
  connection_criteria: Schema.optional(ConnectionCriteriaGroupNodeSchema),
  endpoint_criteria: Schema.optional(
    Schema.suspend((): Schema.Schema<EntityCriteriaGroupNode> => EntityCriteriaGroupNodeSchema),
  ),
  negate: Schema.optional(Schema.Boolean),
  include_potential: Schema.optional(Schema.Boolean),
  max_hops: Schema.optional(Schema.Number),
})

export const EntityCriteriaGroupNodeSchema: Schema.Schema<EntityCriteriaGroupNode> = Schema.Struct({
  kind: Schema.Literal('group'),
  conjunction: Schema.Literal('and', 'or'),
  children: Schema.Array(
    Schema.Union(
      AttributeConditionNodeSchema,
      IncidentConnectionNodeSchema,
      Schema.suspend((): Schema.Schema<EntityCriteriaGroupNode> => EntityCriteriaGroupNodeSchema),
    ),
  ),
  negate: Schema.optional(Schema.Boolean),
})

/** An additive population term. Anchors are always the primary result set — an inclusion never
 * chains off another inclusion's results. */
export const NeighborInclusionSpecSchema = Schema.Struct({
  direction: Schema.optional(Schema.Literal('outgoing', 'incoming', 'either')),
  connection_criteria: Schema.optional(ConnectionCriteriaGroupNodeSchema),
  neighbor_criteria: Schema.optional(EntityCriteriaGroupNodeSchema),
  traversal: Schema.optional(Schema.Literal('direct', 'derived')),
  include_potential: Schema.optional(Schema.Boolean),
  max_hops: Schema.optional(Schema.Number),
})

/** Which of the selected entities' connections the result displays. It narrows within the
 * structural invariant and can never widen past it. */
export const ConnectionSelectionSpecSchema = Schema.Struct({
  enabled: Schema.optional(Schema.Boolean),
  criteria: Schema.optional(ConnectionCriteriaGroupNodeSchema),
  traversal: Schema.optional(Schema.Literal('direct', 'derived', 'both')),
  include_potential: Schema.optional(Schema.Boolean),
  max_hops: Schema.optional(Schema.Number),
})

const AggregateKindSchema = Schema.Literal('count', 'min', 'max', 'sum', 'average', 'first', 'last')

export const QueryBindingSpecSchema = Schema.Struct({
  name: Schema.String,
  /** A type *expression*, not a closed vocabulary: `entity[type-slug]` and
   * `tuple[result-type, ...]` are grammar with holes in them. */
  result_type: Schema.String,
  /** `entities`/`connections` — the plural the domain's `BindingSelect` uses and the write path
   *  stores. The singular was declared on both sides and produced by neither. */
  select: Schema.optional(Schema.Literal('entities', 'connections')),
  criteria: Schema.optional(Schema.Union(EntityCriteriaGroupNodeSchema, ConnectionCriteriaGroupNodeSchema)),
  project: Schema.optional(Schema.String),
  aggregate: Schema.optional(AggregateKindSchema),
  tuple: Schema.optional(Schema.Array(Schema.String)),
  include_in_result: Schema.optional(Schema.Boolean),
})

const ParameterLiteralSchema = Schema.Union(Schema.String, Schema.Number, Schema.Boolean)

/** `type` is the element kind and `cardinality` the shape — orthogonal, so a set-valued parameter
 * is not its own type name. `allowed_values` present means a closed vocabulary enforced at bind
 * time; absent means open, and an unmatched value yields an empty result rather than an error. */
export const QueryParameterSpecSchema = Schema.Struct({
  name: Schema.String,
  type: Schema.Literal('string', 'integer', 'number', 'date', 'boolean', 'slug', 'entity-id'),
  cardinality: Schema.optional(Schema.Literal('one', 'many')),
  allowed_values: Schema.optional(Schema.Array(Schema.String)),
  min_items: Schema.optional(Schema.Number),
  /** Written only when the parameter is optional, which is why the literal is `false`. */
  required: Schema.optional(Schema.Literal(false)),
  default: Schema.optional(Schema.Union(ParameterLiteralSchema, Schema.Array(ParameterLiteralSchema))),
  description: Schema.optional(Schema.String),
})

/** A computed attribute addressable as `derived.<name>`. A `security-signal` attribute is
 * batch-fetched and carries only `metric`; the traversal fields are meaningless for it. */
export const DerivedAttributeSpecSchema = Schema.Struct({
  name: Schema.String,
  source: Schema.optional(Schema.Literal('security-signal')),
  metric: Schema.optional(Schema.String),
  direction: Schema.optional(Schema.Literal('outgoing', 'incoming', 'either')),
  traversal: Schema.optional(Schema.Literal('direct', 'derived')),
  include_potential: Schema.optional(Schema.Boolean),
  max_hops: Schema.optional(Schema.Number),
  connection_criteria: Schema.optional(ConnectionCriteriaGroupNodeSchema),
  endpoint_criteria: Schema.optional(EntityCriteriaGroupNodeSchema),
  reduce: Schema.optional(AggregateKindSchema),
  of: Schema.optional(Schema.String),
})

const TraceEndpointTypeSpecSchema = Schema.Struct({ type: Schema.String })

const TraceStoredEdgeSpecSchema = Schema.Struct({
  kind: Schema.String,
  connection: Schema.String,
  direction: Schema.String,
  endpoint: TraceEndpointTypeSpecSchema,
})

const TraceDiagnosticEdgeSpecSchema = Schema.Struct({
  kind: Schema.String,
  connection: Schema.String,
  direction: Schema.String,
  endpoint: TraceEndpointTypeSpecSchema,
  status: Schema.String,
})

const TraceLeafSpecSchema = Schema.Struct({
  kind: Schema.String,
  connection: Schema.optional(Schema.String),
  traversal: Schema.optional(Schema.String),
  max_hops: Schema.optional(Schema.Number),
  endpoint: Schema.optional(Schema.Union(
    Schema.Struct({ registry: Schema.String }),
    Schema.Struct({ domain: Schema.String, class: Schema.optional(Schema.String) }),
  )),
})

/** `branches` is either a `{ ref }` pointer — preserved rather than expanded, since expansion
 * happens at evaluation — or a map of the author's own branch labels to edges. */
export const TracePatternSpecSchema = Schema.Struct({
  name: Schema.String,
  kind: Schema.String,
  applies_to: Schema.Array(Schema.String),
  branches: Schema.Union(
    Schema.Struct({ ref: Schema.String }),
    Schema.Record({ key: Schema.String, value: TraceStoredEdgeSpecSchema }),
  ),
  leaf: TraceLeafSpecSchema,
  shortcuts: Schema.optional(Schema.Array(TraceDiagnosticEdgeSpecSchema)),
  /** Verdict-neutral: the pattern observes, and its absence is neither a pass nor a gap. */
  diagnostic: Schema.optional(Schema.Boolean),
})

/** `entity_criteria` is always present — an unfiltered query still says so with an empty group,
 * because an absent tree and one matching everything are different claims. */
export const ViewpointQuerySpecSchema = Schema.Struct({
  query_schema: Schema.Number,
  entity_criteria: EntityCriteriaGroupNodeSchema,
  include_connected: Schema.optional(Schema.Array(NeighborInclusionSpecSchema)),
  connections: Schema.optional(ConnectionSelectionSpecSchema),
  repo_scope: Schema.optional(Schema.Literal('enterprise', 'engagement', 'both')),
  bindings: Schema.optional(Schema.Array(QueryBindingSpecSchema)),
  parameters: Schema.optional(Schema.Array(QueryParameterSpecSchema)),
  derived: Schema.optional(Schema.Array(DerivedAttributeSpecSchema)),
  trace_patterns: Schema.optional(Schema.Array(TracePatternSpecSchema)),
})
export type ViewpointQuerySpec = typeof ViewpointQuerySpecSchema.Type

export const ColumnSpecSchema = Schema.Struct({ label: Schema.String, source: Schema.String })

/** `minimum` inclusive, `maximum` exclusive; either is absent when unbounded, which is how the
 * parser reads it back — an omitted bound is "no bound", never an unknown one. */
export const RangeBandSpecSchema = Schema.Struct({
  minimum: Schema.optional(Schema.Number),
  maximum: Schema.optional(Schema.Number),
  value: Schema.String,
})

/** Three modes, each using a different subset of the fields; switching mode clears the others', so
 * a rule never carries two modes' worth of intent. `disabled` is quarantine — saveable exactly as
 * inherited but never evaluated. */
export const StyleRuleSpecSchema = Schema.Struct({
  capability: Schema.String,
  applies_to: Schema.optional(Schema.Array(Schema.String)),
  /** Absent means `match`, which is the default the canonical form omits. */
  mode: Schema.optional(Schema.Literal('range', 'scale')),
  match_criteria: Schema.optional(Schema.Union(EntityCriteriaGroupNodeSchema, ConnectionCriteriaGroupNodeSchema)),
  value: Schema.optional(Schema.String),
  range_attribute: Schema.optional(Schema.String),
  range_bands: Schema.optional(Schema.Array(RangeBandSpecSchema)),
  scale_attribute: Schema.optional(Schema.String),
  scale_min: Schema.optional(Schema.Union(Schema.Number, Schema.String)),
  scale_max: Schema.optional(Schema.Union(Schema.Number, Schema.String)),
  scale_tokens: Schema.optional(Schema.Array(Schema.String)),
  source_criteria: Schema.optional(EntityCriteriaGroupNodeSchema),
  target_criteria: Schema.optional(EntityCriteriaGroupNodeSchema),
  disabled: Schema.optional(Schema.Boolean),
})

/** A closed set, not a map: all three are enumerated vocabularies the save-time validator checks,
 * so an option it does not know is an error rather than a hint a renderer might honour. */
export const DisplayOptionsSpecSchema = Schema.Struct({
  layout: Schema.optional(Schema.Literal('clusters', 'radial', 'force')),
  color_by: Schema.optional(Schema.Literal('domain', 'hop-distance')),
  label_attribute: Schema.optional(Schema.String),
})

/** Additive on the query and never part of it: two presentations of one query select the same
 * entities, so a summary or a count never depends on this level. */
export const PresentationSpecWireSchema = Schema.Struct({
  representation: Schema.Literal('exploration', 'table', 'matrix', 'diagram'),
  display_options: Schema.optional(DisplayOptionsSpecSchema),
  columns: Schema.optional(Schema.Array(ColumnSpecSchema)),
  row_by: Schema.optional(Schema.String),
  column_by: Schema.optional(Schema.String),
  row_criteria: Schema.optional(EntityCriteriaGroupNodeSchema),
  column_criteria: Schema.optional(EntityCriteriaGroupNodeSchema),
  group_by: Schema.optional(Schema.String),
  /** Ordered, first match wins per capability — which is what makes a later rule *shadowed*. */
  styling_rules: Schema.optional(Schema.Array(StyleRuleSpecSchema)),
  default_style: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.String })),
  target_types: Schema.optional(Schema.Array(Schema.String)),
  legibility_budget: Schema.optional(Schema.Number),
  aggregate_by: Schema.optional(Schema.String),
})
export type PresentationSpecWire = typeof PresentationSpecWireSchema.Type
