import { Schema } from 'effect'

import { BrokenReferenceSchema } from './viewpointReferences'
import { TraceTableSchema } from './viewpointTrace'

export type { PatternResult, TraceObligation, TraceRow, TraceTable } from './viewpointTrace'
export { CriteriaCatalogSchema, type CriteriaCatalog } from './viewpointCatalogs'

// ── Viewpoints (GUI selector/overlay) ─────────────────────────────────────────

export const ViewpointApplicationSchema = Schema.Struct({
  slug: Schema.String,
  version: Schema.Number,
  enforcement_override: Schema.optional(Schema.Literal('off', 'warn', 'ghost')),
  derivation_params: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
})
export type ViewpointApplication = typeof ViewpointApplicationSchema.Type

export const ViewpointSummarySchema = Schema.Struct({
  slug: Schema.String,
  version: Schema.Number,
  name: Schema.String,
  description: Schema.String,
  purpose: Schema.Array(Schema.String),
  content: Schema.Array(Schema.String),
  scope: Schema.Unknown,
})
export type ViewpointSummary = typeof ViewpointSummarySchema.Type

export type {
  DiagramViewpointProjection,
  ProjectedOccurrence,
  ScaleLegendData,
  ScaleStyleValue,
  StyleRuleOutcome,
  StyleValue,
  ViewpointProjection,
} from './viewpointProjection'
export {
  AppliedDiagramViewpointSchema,
  DiagramViewpointProjectionSchema,
  NoDiagramViewpointSchema,
  ProjectedOccurrenceSchema,
  ScaleLegendDataSchema,
  ScaleStyleValueSchema,
  StyleRuleOutcomeSchema,
  StyleValueSchema,
  ViewpointProjectionSchema,
} from './viewpointProjection'


// ── Viewpoint execution ────────────────────────────────────────────────────────
// Fixed, non-customizable per-item summaries — deliberately unstyled.
// Style tokens come from the separate `execute-projection` endpoint (`ViewpointProjectionSchema`
// above), never from this contract, so MCP/REST content can never disagree with the GUI.

export const EntityItemSummarySchema = Schema.Struct({
  id: Schema.String,
  name: Schema.String,
  type: Schema.String,
  specialization_slugs: Schema.Array(Schema.String),
  group: Schema.String,
  /** Ontology domain of the entity's type. Optional-with-default so a client tolerates a
   * backend that predates the field rather than failing the whole execution decode. */
  domain: Schema.optionalWith(Schema.String, { default: () => '' }),
  membership: Schema.Literal('primary', 'expanded'),
  status: Schema.optionalWith(Schema.String, { default: () => '' }),
  version: Schema.optionalWith(Schema.String, { default: () => '' }),
  /** Present when the definition authors table columns: one entry per column source,
   * resolved server-side at the execution's snapshot; a source with no value for this
   * entity is explicitly null. */
  column_values: Schema.optionalWith(
    Schema.NullOr(Schema.Record({ key: Schema.String, value: Schema.NullOr(Schema.Unknown) })),
    { default: () => null },
  ),
  /** Modeled hop distance from the nearest anchor (0 = anchor, 1 = direct modeled edge,
   * N = minimum derived witness-chain length). Null/absent when the execution is
   * unanchored or the entity has no connecting edge to any anchor (unranked — rendered
   * as its own state, never as distance 0 or 1). */
  anchor_modeled_distance: Schema.optionalWith(Schema.NullOr(Schema.Number), { default: () => null }),
  /** Set when this entity's criteria match required derived-relationship evidence: the
   * minimum witness-chain length the verdict rested on. Null when the match holds on
   * modeled facts alone — surfaces tag such rows "matched via derived (N hops)". */
  matched_via_derived_hops: Schema.optionalWith(Schema.NullOr(Schema.Number), { default: () => null }),
})
export type EntityItemSummary = typeof EntityItemSummarySchema.Type

/** One step of a derived connection's witness chain, already ordered source→target by
 * the server (`via_connection_ids` is unordered membership and never renderable as-is). */
export const WitnessStepSchema = Schema.Struct({
  connection_id: Schema.String,
  source: Schema.String,
  target: Schema.String,
  connection_type: Schema.String,
  direction: Schema.Literal('forward', 'reverse'),
  hop_index: Schema.Number,
})
export type WitnessStep = typeof WitnessStepSchema.Type

export const ConnectionItemSummarySchema = Schema.Struct({
  id: Schema.String,
  type: Schema.String,
  source: Schema.String,
  target: Schema.String,
  certainty: Schema.NullOr(Schema.Literal('certain', 'potential')),
  hops: Schema.NullOr(Schema.Number),
  via_connection_ids: Schema.Array(Schema.String),
  /** Empty for modeled connections, and for a derived connection whose chain could not
   * be reconstructed (renderers show that as "chain unavailable", never as no chain). */
  witness_steps: Schema.optionalWith(Schema.Array(WitnessStepSchema), { default: () => [] }),
})
export type ConnectionItemSummary = typeof ConnectionItemSummarySchema.Type

export const MatrixAxisIdsSchema = Schema.Struct({
  row_entity_ids: Schema.Array(Schema.String),
  column_entity_ids: Schema.Array(Schema.String),
})
export type MatrixAxisIds = typeof MatrixAxisIdsSchema.Type

/** Classification of the FULL result against the definition's declared target
 * population — absent when the target population is unknown, in which case headers show
 * plain counts and make NO absence claims. */
export const AggregateNodeSchema = Schema.Struct({
  id: Schema.String,
  dimension: Schema.Literal('group', 'domain', 'type'),
  dimension_value: Schema.String,
  entity_type: Schema.String,
  member_count: Schema.Number,
  member_ids: Schema.Array(Schema.String),
})
export type AggregateNode = typeof AggregateNodeSchema.Type

export const AggregateEdgeSchema = Schema.Struct({
  id: Schema.String,
  source_aggregate_id: Schema.String,
  target_aggregate_id: Schema.String,
  connection_type: Schema.String,
  provenance: Schema.Literal('modeled', 'derived-certain', 'derived-potential'),
  member_count: Schema.Number,
  member_connection_ids: Schema.Array(Schema.String),
})
export type AggregateEdge = typeof AggregateEdgeSchema.Type

/** Present when the complete population exceeds the effective legibility budget on a
 * graph surface: the super-nodes and bundled edges the surface opens with. */
export const AggregationSummarySchema = Schema.Struct({
  dimension: Schema.Literal('group', 'domain', 'type'),
  legibility_budget: Schema.Number,
  nodes: Schema.Array(AggregateNodeSchema),
  edges: Schema.Array(AggregateEdgeSchema),
})
export type AggregationSummary = typeof AggregationSummarySchema.Type

export const TargetPopulationSummarySchema = Schema.Struct({
  target_types: Schema.Array(Schema.String),
  target_count: Schema.Number,
  incidental_type_counts: Schema.Record({ key: Schema.String, value: Schema.Number }),
  structural_count: Schema.Number,
})
export type TargetPopulationSummary = typeof TargetPopulationSummarySchema.Type

export const ViewpointExecutionResultSchema = Schema.Struct({
  slug: Schema.NullOr(Schema.String),
  version: Schema.NullOr(Schema.Number),
  query_schema: Schema.Number,
  repo_scope: Schema.String,
  executed_at: Schema.String,
  index_generation: Schema.NullOr(Schema.Number),
  entity_ids: Schema.Array(Schema.String),
  connection_ids: Schema.Array(Schema.String),
  entities: Schema.Array(EntityItemSummarySchema),
  connections: Schema.Array(ConnectionItemSummarySchema),
  total_entity_count: Schema.Number,
  returned_entity_count: Schema.Number,
  total_connection_count: Schema.Number,
  returned_connection_count: Schema.Number,
  truncated: Schema.Boolean,
  entity_limit: Schema.Number,
  matrix_axes: Schema.NullOr(MatrixAxisIdsSchema),
  warnings: Schema.Array(Schema.String),
  duration_ms: Schema.Number,
  query_summary: Schema.String,
  /** Entity ids the execution was anchored on (resolved `entity-id` parameter values) —
   * presentations mark/center these and derive hop distances from them. */
  anchor_ids: Schema.optionalWith(Schema.Array(Schema.String), { default: () => [] }),
  target_population: Schema.optionalWith(Schema.NullOr(TargetPopulationSummarySchema), { default: () => null }),
  aggregation: Schema.optionalWith(Schema.NullOr(AggregationSummarySchema), { default: () => null }),
  /** The canonical values this execution ran with — what a shared URL must reproduce. A
   * parameter declares a scalar element kind and a cardinality, and a set-valued one
   * canonicalizes to strings, so these arms are the whole value space binding produces. */
  bound_parameters: Schema.optionalWith(
    Schema.Record({
      key: Schema.String,
      value: Schema.Union(Schema.Boolean, Schema.Number, Schema.String, Schema.Array(Schema.String)),
    }),
    { default: () => ({}) },
  ),
  trace_table: Schema.optionalWith(Schema.NullOr(TraceTableSchema), { default: () => null }),
})
export type ViewpointExecutionResult = typeof ViewpointExecutionResultSchema.Type

export interface ViewpointExecutionRequest {
  readonly slug?: string
  readonly query?: unknown
  readonly limit?: number
  readonly parameters?: Record<string, unknown>
  // Optional, additive on both paths: the inline presentation for a `query`, or an ephemeral
  // override for a `slug` (the stored definition is never mutated). Serialized presentation
  // mapping — the same shape a saved definition's presentation uses.
  readonly presentation?: unknown
}

/** GUI-only ad-hoc ArchiMate-notation rendering (the ad-hoc `diagram` representation) —
 * unstyled; `node_color`/`edge_color`/`edge_emphasis` overlays are applied client-side
 * onto the returned SVG. */
export const SignalBannerSchema = Schema.Struct({
  classification: Schema.NullOr(Schema.String),
  available: Schema.Boolean,
  note: Schema.NullOr(Schema.String),
  basis_snapshots: Schema.Array(Schema.Struct({
    anchor_entity_id: Schema.String,
    snapshot_id: Schema.String,
    activated_at: Schema.String,
  })),
  generated_at: Schema.String,
})
export type SignalBanner = typeof SignalBannerSchema.Type

export const ViewpointDiagramResultSchema = Schema.Struct({
  svg: Schema.NullOr(Schema.String),
  warnings: Schema.Array(Schema.String),
  // Entity id -> the rendered SVG's PlantUML alias (never the raw artifact id) — needed to
  // resolve SVG elements back to artifact ids for click-to-select, the same way a real
  // persisted diagram's viewer already does from its own diagram_entities.
  entity_aliases: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.String })),
  // Present ONLY for definitions declaring a security-signal source: computed
  // classification + basis snapshots + generation timestamp (the D11 ephemeral render).
  signal_banner: Schema.optional(Schema.NullOr(SignalBannerSchema)),
})
export type ViewpointDiagramResult = typeof ViewpointDiagramResultSchema.Type

// ── Viewpoint definitions (management view) ───────────────────────────────────
// `query`/`presentation`/`scope` stay `Unknown` here (matching the existing
// `ViewpointSummarySchema.scope` convention above) — their recursive wire shape is
// modeled by plain TS types in `viewpointCriteria.ts`, decoded/encoded by
// `viewpointCriteriaSerialization.ts`, not by Effect Schema.

export const ScopeSummarySchema = Schema.Struct({
  unrestricted: Schema.Boolean,
  entity_types: Schema.optional(Schema.Array(Schema.String)),
  connection_types: Schema.optional(Schema.Array(Schema.String)),
  excluded_entity_types: Schema.optional(Schema.Array(Schema.String)),
  excluded_domains: Schema.optional(Schema.Array(Schema.String)),
  excluded_connection_types: Schema.optional(Schema.Array(Schema.String)),
})
export type ScopeSummary = typeof ScopeSummarySchema.Type

export const ViewpointDefinitionEnvelopeSchema = Schema.Struct({
  slug: Schema.String,
  version: Schema.Number,
  name: Schema.String,
  description: Schema.optional(Schema.String),
  rationale: Schema.optional(Schema.String),
  purpose: Schema.optional(Schema.Union(Schema.String, Schema.Array(Schema.String))),
  content: Schema.optional(Schema.Union(Schema.String, Schema.Array(Schema.String))),
  stakeholders: Schema.optional(Schema.Array(Schema.String)),
  concerns: Schema.optional(Schema.Array(Schema.String)),
  scope: Schema.optional(Schema.Unknown),
  representation_types: Schema.optional(Schema.Array(Schema.String)),
  derivation_defaults: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  query: Schema.optional(Schema.Unknown),
  presentation: Schema.optional(Schema.Unknown),
  // Which selection layer is ACTIVE (scope | query); absent on pre-migration definitions,
  // where the legacy behavior (query when present, else scope) applies.
  selection_mode: Schema.optional(Schema.Literal('scope', 'query')),
  /** Fork provenance, stamped server-side at fork time (origin slug/version/content
   * digest); absent on non-forks. */
  forked_from: Schema.optional(Schema.Struct({
    slug: Schema.String,
    version: Schema.Number,
    definition_digest: Schema.String,
    index_generation: Schema.optional(Schema.Number),
  })),
  /** Digest-computed staleness against the CURRENT origin — 'stale' the moment the
   * origin's content changes, even without a version bump. Null for non-forks. */
  fork_status: Schema.optionalWith(
    Schema.NullOr(Schema.Literal('current', 'stale', 'origin-missing')),
    { default: () => null },
  ),
  // The definition's CURRENT canonical content digest — verified execution references pin
  // it so a later open can say the definition changed.
  definition_digest: Schema.optional(Schema.String),
  tier: Schema.Literal('module', 'enterprise', 'engagement'),
  scope_summary: ScopeSummarySchema,
  query_summary: Schema.NullOr(Schema.String),
  // Broken references, computed on demand and never persisted; optional so an older
  // backend (or a hand-built fixture) decodes cleanly. Treat absent as none.
  broken_references: Schema.optional(Schema.Array(BrokenReferenceSchema)),
})
export type ViewpointDefinitionEnvelope = typeof ViewpointDefinitionEnvelopeSchema.Type

export const ViewpointDefinitionListSchema = Schema.Struct({
  viewpoints: Schema.Array(ViewpointDefinitionEnvelopeSchema),
})

export const ViewpointSummarizeResultSchema = Schema.Struct({ summary: Schema.String })

export const ViewpointValidationIssueSchema = Schema.Struct({
  severity: Schema.Literal('error', 'warning'),
  code: Schema.String,
  path: Schema.String,
  message: Schema.String,
  expected: Schema.NullOr(Schema.String),
  found: Schema.NullOr(Schema.String),
})
export type ViewpointValidationIssue = typeof ViewpointValidationIssueSchema.Type

export const ViewpointReferencerSchema = Schema.Struct({
  artifact_id: Schema.String,
  target_kind: Schema.Literal('diagram', 'matrix'),
})
export type ViewpointReferencer = typeof ViewpointReferencerSchema.Type

export const ViewpointReferencerListSchema = Schema.Struct({
  referencers: Schema.Array(ViewpointReferencerSchema),
})

/** `pruned` slugs were pinned but have since dropped out of the effective catalog (e.g. a
 * deleted engagement-repo definition) — reported so the GUI can surface that a pin was
 * silently dropped, rather than the pin list just quietly shrinking. Only `GET` reports
 * it; `PUT`'s response echoes just the saved `slugs`. */
export const ViewpointPinsSchema = Schema.Struct({
  slugs: Schema.Array(Schema.String),
  pruned: Schema.optional(Schema.Array(Schema.String)),
})
export type ViewpointPins = typeof ViewpointPinsSchema.Type

export const ViewpointPersistResultSchema = Schema.Struct({
  ok: Schema.Boolean,
  action: Schema.Literal('create', 'edit', 'delete'),
  slug: Schema.String,
  version: Schema.NullOr(Schema.Number),
  dry_run: Schema.Boolean,
  issues: Schema.Array(ViewpointValidationIssueSchema),
  referencers: Schema.Array(ViewpointReferencerSchema),
})
export type ViewpointPersistResult = typeof ViewpointPersistResultSchema.Type
