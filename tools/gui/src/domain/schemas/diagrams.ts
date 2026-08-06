import { Schema } from 'effect'
import { ViewpointApplicationSchema } from './viewpoints'
import { EntityContextConnectionSchema } from './connections'
import { EntityDisplayInfoSchema } from './entities'

/**
 * One labelled box a diagram draws that the model does not hold.
 *
 * Recursive, because boxes nest. `entity-ids` keeps its frontmatter spelling on the wire, so what is
 * read is what is written back, and a member may name an entity or a single occurrence of one.
 */
export interface AuthoredGroupingWire {
  readonly label: string
  readonly 'entity-ids': readonly string[]
  readonly groups?: readonly AuthoredGroupingWire[]
  /** An override the backend still honours; the look is otherwise derived from the members. */
  readonly stereotype?: string
}

export const AuthoredGroupingSchema: Schema.Schema<AuthoredGroupingWire> = Schema.Struct({
  label: Schema.String,
  'entity-ids': Schema.Array(Schema.String),
  groups: Schema.optional(Schema.Array(Schema.suspend(() => AuthoredGroupingSchema))),
  stereotype: Schema.optional(Schema.String),
})

export const DiagramDetailSchema = Schema.Struct({
  artifact_id: Schema.String,
  artifact_type: Schema.String,
  name: Schema.String,
  diagram_type: Schema.String,
  version: Schema.String,
  status: Schema.String,
  record_type: Schema.Literal('diagram'),
  path: Schema.String,
  is_global: Schema.Boolean,
  group: Schema.optional(Schema.String),
  last_updated: Schema.optional(Schema.String),
  content_snippet: Schema.String,
  puml_source: Schema.String,
  /** Absent when nothing has been rendered yet. */
  rendered_filename: Schema.optional(Schema.String),
  entity_ids_used: Schema.optional(Schema.Array(Schema.String)),
  connection_ids_used: Schema.optional(Schema.Array(Schema.String)),
  diagram_entities: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  /** The labelled boxes the diagram draws that the model does not hold. Read as well as written,
   * because an editor that could author one without seeing the existing ones would replace them. */
  authored_groupings: Schema.optional(Schema.Array(AuthoredGroupingSchema)),
  extra: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  /** This diagram kind's own additions — a matrix's rendered body, and whatever a future kind
   * contributes. Absent for a kind that adds nothing. */
  type_extras: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  viewpoint: Schema.optional(ViewpointApplicationSchema),
})
export type DiagramDetail = typeof DiagramDetailSchema.Type

// ── Matrix diagram ───────────────────────────────────────────────────────────

export const MatrixConnTypeConfigSchema = Schema.Struct({
  conn_type: Schema.String,
  active: Schema.Boolean,
})
export type MatrixConnTypeConfig = typeof MatrixConnTypeConfigSchema.Type

export const MatrixConfigSchema = Schema.Struct({
  artifact_id: Schema.String,
  name: Schema.String,
  status: Schema.String,
  version: Schema.String,
  keywords: Schema.Array(Schema.String),
  entity_ids: Schema.Array(Schema.String),
  // Present and null for a square matrix, never absent: the route emits both keys unconditionally, and
  // null says "no separate axis was authored" — a statement the absent case cannot make.
  from_entity_ids: Schema.NullOr(Schema.Array(Schema.String)),
  to_entity_ids: Schema.NullOr(Schema.Array(Schema.String)),
  conn_type_configs: Schema.Array(MatrixConnTypeConfigSchema),
  combined: Schema.Boolean,
  matrix_body: Schema.String,
})
export type MatrixConfig = typeof MatrixConfigSchema.Type

export const MatrixPreviewResultSchema = Schema.Struct({
  markdown: Schema.String,
})
export type MatrixPreviewResult = typeof MatrixPreviewResultSchema.Type

export const C4NavLinkSchema = Schema.Struct({
  diagram_id: Schema.String,
  diagram_name: Schema.String,
  diagram_type: Schema.String,
  scope_entity_id: Schema.optional(Schema.NullOr(Schema.String)),
})
export type C4NavLink = typeof C4NavLinkSchema.Type

export const C4NavigationSchema = Schema.Struct({
  current_level: Schema.Number,
  scope_entity_id: Schema.NullOr(Schema.String),
  scope_entity_name: Schema.NullOr(Schema.String),
  parent_diagrams: Schema.Array(C4NavLinkSchema),
  child_diagrams: Schema.Array(C4NavLinkSchema),
})
export type C4Navigation = typeof C4NavigationSchema.Type

/** One entity as this diagram places it: the list row, plus the alias it is drawn under.
 *
 * A struct of its own rather than `EntitySummarySchema`, which is the *list* row and carries
 * several optional fields no diagram read fills. `display_alias` is required here because only a
 * diagram read resolves it. */
export const DiagramContextEntitySchema = Schema.Struct({
  artifact_id: Schema.String,
  artifact_type: Schema.String,
  name: Schema.String,
  version: Schema.String,
  status: Schema.String,
  domain: Schema.String,
  subdomain: Schema.String,
  path: Schema.String,
  is_global: Schema.Boolean,
  display_alias: Schema.String,
  group: Schema.optional(Schema.String),
  specializations: Schema.Array(Schema.String),
  host_diagram_id: Schema.optional(Schema.String),
  conn_in: Schema.optional(Schema.Number),
  conn_sym: Schema.optional(Schema.Number),
  conn_out: Schema.optional(Schema.Number),
  last_updated: Schema.optional(Schema.String),
})
export type DiagramContextEntity = typeof DiagramContextEntitySchema.Type

/** One connection as this diagram draws it: the record, plus its rendered identity here.
 *
 * The aliases and `edge_key` locate the drawn line in *this* file, and
 * `edge_label_override` is the label the author set for that edge — it belongs to the diagram, not
 * to the connection, since the same connection drawn twice can carry two labels. */
export const DiagramContextConnectionSchema = Schema.Struct({
  artifact_id: Schema.String,
  source: Schema.String,
  target: Schema.String,
  conn_type: Schema.String,
  version: Schema.String,
  status: Schema.String,
  path: Schema.String,
  content_text: Schema.String,
  associated_entities: Schema.Array(Schema.String),
  source_name: Schema.String,
  target_name: Schema.String,
  source_alias: Schema.String,
  target_alias: Schema.String,
  edge_key: Schema.String,
  edge_label_override: Schema.optional(Schema.String),
  src_multiplicity: Schema.optional(Schema.String),
  tgt_multiplicity: Schema.optional(Schema.String),
  specializations: Schema.Array(Schema.String),
  metadata: Schema.Record({ key: Schema.String, value: Schema.Unknown }),
  gar_artifact_id: Schema.optional(Schema.String),
})
export type DiagramContextConnection = typeof DiagramContextConnectionSchema.Type

/** Entities one hop further out than the last group. `hop` starts at 1 — hop 0 is what the
 * diagram already holds. */
export const HopSuggestionGroupSchema = Schema.Struct({
  hop: Schema.Number,
  items: Schema.Array(EntityDisplayInfoSchema),
})

export const DiagramContextSchema = Schema.Struct({
  diagram: DiagramDetailSchema,
  entities: Schema.Array(DiagramContextEntitySchema),
  connections: Schema.Array(DiagramContextConnectionSchema),
  candidate_connections: Schema.Array(EntityContextConnectionSchema),
  suggested_entities: Schema.Array(HopSuggestionGroupSchema),
  /** Source/target alias pairs the PUML actually draws — how a stated connection is told from
   * one that merely exists between two placed entities. */
  explicit_connection_pairs: Schema.Array(Schema.Tuple(Schema.String, Schema.String)),
  generation: Schema.Number,
  etag: Schema.String,
  /** This diagram kind's own additions — a C4 diagram's navigation, and whatever a future kind
   * contributes. Absent for a kind that adds nothing. */
  type_extras: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
})
export type DiagramContext = typeof DiagramContextSchema.Type

export const DiagramEntityDiscoverySchema = Schema.Struct({
  search_results: Schema.Array(EntityDisplayInfoSchema),
  candidate_connections: Schema.Array(EntityContextConnectionSchema),
  suggested_entities: Schema.Array(HopSuggestionGroupSchema),
})
export type DiagramEntityDiscovery = typeof DiagramEntityDiscoverySchema.Type

/** One entity a model-backed diagram derived rather than the author placing it.
 *
 * `item_type` and `role` are the diagram-type module's vocabulary and are forwarded, never
 * interpreted. `role` is load-bearing all the same: the scope root arrives as `scope` and the
 * engine will not exclude it, so a checklist offering to uncheck it offers nothing. Both fields
 * were absent here and stripped on decode, which is why that has gone unnoticed. */
export const DerivedEntitySchema = Schema.Struct({
  id: Schema.String,
  name: Schema.String,
  item_type: Schema.String,
  role: Schema.String,
  excluded: Schema.Boolean,
})
export type DerivedEntity = typeof DerivedEntitySchema.Type

export const DiagramPreviewResultSchema = Schema.Struct({
  puml: Schema.String,
  image: Schema.NullOr(Schema.String),
  warnings: Schema.Array(Schema.String),
  derived_entities: Schema.NullOr(Schema.Array(DerivedEntitySchema)),
})
export type DiagramPreviewResult = typeof DiagramPreviewResultSchema.Type
