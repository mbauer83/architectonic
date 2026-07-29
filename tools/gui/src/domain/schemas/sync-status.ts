import { Schema } from 'effect'

export const SyncLifecycleSchema = Schema.Literal('synced', 'accumulating', 'pending')
export type SyncLifecycle = typeof SyncLifecycleSchema.Type

export const SyncHealthReasonSchema = Schema.Literal(
  'fetch_failed',
  'upstream_missing',
  'diverged',
  'sync_state_unknown',
  'state_file_corrupt',
  'repository_uninitialized',
)
export type SyncHealthReason = typeof SyncHealthReasonSchema.Type

export const SyncHealthSchema = Schema.Struct({
  reason: SyncHealthReasonSchema,
  message: Schema.String,
  observed_at: Schema.String,
})
export type SyncHealth = typeof SyncHealthSchema.Type

export const BlockKindSchema = Schema.Literal('none', 'read_only', 'sync_in_progress', 'sync_health')
export type BlockKind = typeof BlockKindSchema.Type

export const DeniedIntentSchema = Schema.Struct({
  denied: Schema.Boolean,
  code: Schema.NullOr(Schema.String),
})
export type DeniedIntent = typeof DeniedIntentSchema.Type

/** Per-intent authority projection, composed fresh by the backend on every
 * status request — never cached, never derived client-side from SSE. */
export const SyncAuthoritySchema = Schema.Struct({
  block_kind: BlockKindSchema,
  blocked_reason: Schema.NullOr(SyncHealthReasonSchema),
  blocked_message: Schema.NullOr(Schema.String),
  denied_intents: Schema.Record({ key: Schema.String, value: DeniedIntentSchema }),
})
export type SyncAuthority = typeof SyncAuthoritySchema.Type

export const EngagementSyncStatusSchema = Schema.Struct({
  has_uncommitted_changes: Schema.Boolean,
})
export type EngagementSyncStatus = typeof EngagementSyncStatusSchema.Type

export const EnterpriseSyncStatusSchema = Schema.Struct({
  status: SyncLifecycleSchema,
  label: Schema.String,
  branch: Schema.NullOr(Schema.String),
  branch_tip: Schema.NullOr(Schema.String),
  pushed_at: Schema.NullOr(Schema.String),
  commits_behind: Schema.NullOr(Schema.Number),
  commits_ahead: Schema.optional(Schema.NullOr(Schema.Number)),
  has_uncommitted_changes: Schema.Boolean,
  health: Schema.NullOr(SyncHealthSchema),
})
export type EnterpriseSyncStatus = typeof EnterpriseSyncStatusSchema.Type

export const SyncStatusSchema = Schema.Struct({
  engagement: Schema.NullOr(EngagementSyncStatusSchema),
  enterprise: Schema.NullOr(EnterpriseSyncStatusSchema),
  authority: SyncAuthoritySchema,
})
export type SyncStatus = typeof SyncStatusSchema.Type

export const SyncSaveResultSchema = Schema.Struct({
  ok: Schema.Boolean,
  commit: Schema.optional(Schema.String),
  pushed: Schema.optional(Schema.Boolean),
  message: Schema.optional(Schema.String),
  branch: Schema.optional(Schema.String),
  discarded_branch: Schema.optional(Schema.String),
  already_submitted: Schema.optional(Schema.Boolean),
})
export type SyncSaveResult = typeof SyncSaveResultSchema.Type
