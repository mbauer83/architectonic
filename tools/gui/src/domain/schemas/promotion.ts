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
  structural_closure: Schema.optionalWith(Schema.Array(StructuralClosureRequirementSchema), { default: () => [] }),
  group_mapping: Schema.optional(Schema.Array(PromotionGroupMappingEntrySchema)),
  available_enterprise_groups: Schema.optional(Schema.Array(Schema.Struct({
    slug: Schema.String,
    id: Schema.String,
    name: Schema.String,
  }))),
})
export type PromotionPlan = typeof PromotionPlanSchema.Type

export const PromotionResultSchema = Schema.Struct({
  dry_run: Schema.Boolean,
  executed: Schema.Boolean,
  copied_files: Schema.Array(Schema.String),
  updated_files: Schema.Array(Schema.String),
  verification_errors: Schema.Array(Schema.String),
  rolled_back: Schema.Boolean,
})
export type PromotionResult = typeof PromotionResultSchema.Type
