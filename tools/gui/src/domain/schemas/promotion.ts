import { Schema } from 'effect'

export const PromotionConflictSchema = Schema.Struct({
  engagement_id: Schema.String,
  enterprise_id: Schema.String,
  artifact_type: Schema.String,
  engagement_name: Schema.String,
  enterprise_name: Schema.String,
  engagement_fields: Schema.Record({ key: Schema.String, value: Schema.Unknown }),
  enterprise_fields: Schema.Record({ key: Schema.String, value: Schema.Unknown }),
})
export type PromotionConflict = typeof PromotionConflictSchema.Type

export const PromotionDocumentConflictSchema = Schema.Struct({
  engagement_id: Schema.String,
  enterprise_id: Schema.String,
  doc_type: Schema.String,
  engagement_title: Schema.String,
  enterprise_title: Schema.String,
})
export type PromotionDocumentConflict = typeof PromotionDocumentConflictSchema.Type

export const PromotionDiagramConflictSchema = Schema.Struct({
  engagement_id: Schema.String,
  enterprise_id: Schema.String,
  diagram_type: Schema.String,
  engagement_name: Schema.String,
  enterprise_name: Schema.String,
})
export type PromotionDiagramConflict = typeof PromotionDiagramConflictSchema.Type

export const PromotionGroupMappingEntrySchema = Schema.Struct({
  engagement_slug: Schema.String,
  engagement_group_id: Schema.String,
  match_status: Schema.Literal('matched_by_id', 'conflict', 'new'),
  enterprise_slug: Schema.String,
  enterprise_group_id: Schema.NullOr(Schema.String),
})
export type PromotionGroupMappingEntry = typeof PromotionGroupMappingEntrySchema.Type

export const StructuralClosureEntitySchema = Schema.Struct({
  artifact_id: Schema.String,
  name: Schema.String,
  artifact_type: Schema.String,
})
export type StructuralClosureEntity = typeof StructuralClosureEntitySchema.Type

/** One selected junction/grouping whose meaning-carrying entities are missing from the
 * promotion selection — the GUI offers a one-action "include the missing entities" flow
 * from exactly this data. */
export const StructuralClosureRequirementSchema = Schema.Struct({
  entity_id: Schema.String,
  entity_name: Schema.String,
  kind: Schema.Literal('junction', 'grouping'),
  missing: Schema.Array(StructuralClosureEntitySchema),
})
export type StructuralClosureRequirement = typeof StructuralClosureRequirementSchema.Type

/** A viewpoint a promoted diagram or matrix is pinned to. `enterprise_version` null means it is not
 *  there at all — the case that forces a choice between promoting it alongside and repinning. */
export const PromotionViewpointDependencySchema = Schema.Struct({
  target_id: Schema.String,
  target_kind: Schema.String,
  slug: Schema.String,
  pinned_version: Schema.String,
  status: Schema.String,
  enterprise_version: Schema.NullOr(Schema.String),
})
export type PromotionViewpointDependency = typeof PromotionViewpointDependencySchema.Type

/** An artifact the selection references but does not include, and what needs it. */
export const PromotionMissingDependencySchema = Schema.Struct({
  artifact_id: Schema.String,
  name: Schema.String,
  record_type: Schema.String,
  required_by: Schema.String,
  kind: Schema.String,
})
export type PromotionMissingDependency = typeof PromotionMissingDependencySchema.Type

export const EnterpriseGroupOptionSchema = Schema.Struct({
  slug: Schema.String,
  id: Schema.String,
  name: Schema.String,
})

/**
 * What a promotion would do, and every question it raises before it may proceed.
 *
 * Nothing here is optional now. Four of these lists were, and two were absent outright —
 * `viewpoint_dependencies` and `missing_dependencies`, the two that can make a promotion produce a
 * broken enterprise repository. An empty list and an uncomputed one have to be distinguishable, and
 * only one of them is representable when the key may be missing.
 */
export const PromotionPlanSchema = Schema.Struct({
  entity_id: Schema.String,
  entities_to_add: Schema.Array(Schema.String),
  conflicts: Schema.Array(PromotionConflictSchema),
  connection_ids: Schema.Array(Schema.String),
  already_in_enterprise: Schema.Array(Schema.String),
  warnings: Schema.Array(Schema.String),
  documents_to_add: Schema.Array(Schema.String),
  diagrams_to_add: Schema.Array(Schema.String),
  doc_conflicts: Schema.Array(PromotionDocumentConflictSchema),
  diagram_conflicts: Schema.Array(PromotionDiagramConflictSchema),
  schema_errors: Schema.Array(Schema.String),
  structural_closure: Schema.Array(StructuralClosureRequirementSchema),
  group_mapping: Schema.Array(PromotionGroupMappingEntrySchema),
  available_enterprise_groups: Schema.Array(EnterpriseGroupOptionSchema),
  viewpoint_dependencies: Schema.Array(PromotionViewpointDependencySchema),
  missing_dependencies: Schema.Array(PromotionMissingDependencySchema),
})
export type PromotionPlan = typeof PromotionPlanSchema.Type

export const PromotionResultSchema = Schema.Struct({
  dry_run: Schema.Boolean,
  executed: Schema.Boolean,
  copied_files: Schema.Array(Schema.String),
  updated_files: Schema.Array(Schema.String),
  verification_errors: Schema.Array(Schema.String),
  // The one to read after a failure: the promotion runs in a git worktree transaction, so saying the
  // enterprise repository was restored is what stops an operator cleaning up by hand.
  rolled_back: Schema.Boolean,
  warnings: Schema.Array(Schema.String),
})
export type PromotionResult = typeof PromotionResultSchema.Type
