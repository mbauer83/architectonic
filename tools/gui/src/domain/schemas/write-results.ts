import { Schema } from 'effect'

const UnknownRecord = Schema.Record({ key: Schema.String, value: Schema.Unknown })

/**
 * One finding from the post-write verify. `details` and `actions` stay unknown maps because the rule
 * that raised the finding decides their keys — the server declares them open for the same reason.
 *
 * The three optionals are `optional(NullOr(…))` because the mutation responses do not omit nulls, so
 * the published schema permits either: an issue about the artifact as a whole has no `location`, and
 * most rules attach neither `details` nor `actions`.
 */
export const VerificationIssueSchema = Schema.Struct({
  severity: Schema.Literal('error', 'warning'),
  code: Schema.String,
  message: Schema.String,
  location: Schema.optional(Schema.NullOr(Schema.String)),
  details: Schema.optional(Schema.NullOr(UnknownRecord)),
  actions: Schema.optional(Schema.NullOr(Schema.Array(UnknownRecord))),
})
export type VerificationIssue = typeof VerificationIssueSchema.Type

/**
 * Whether what a mutation wrote verifies. Was `Schema.Unknown`, which made every consumer re-derive
 * the shape defensively at the point of use — a cast in `CreateDiagramView`, two `isRecord` walks in
 * `ui/lib/errors.ts`. The server has always sent these four keys.
 */
export const WriteVerificationSchema = Schema.Struct({
  path: Schema.optional(Schema.NullOr(Schema.String)),
  file_type: Schema.optional(
    Schema.NullOr(Schema.Literal('entity', 'connection', 'diagram', 'document')),
  ),
  valid: Schema.Boolean,
  issues: Schema.Array(VerificationIssueSchema),
})
export type WriteVerification = typeof WriteVerificationSchema.Type

export const WriteResultSchema = Schema.Struct({
  wrote: Schema.Boolean,
  path: Schema.String,
  artifact_id: Schema.String,
  content: Schema.NullOr(Schema.String),
  warnings: Schema.Array(Schema.String),
  verification: Schema.NullOr(WriteVerificationSchema),
})
export type WriteResult = typeof WriteResultSchema.Type

/**
 * `deleted_diagram` is the sync's promise that it left the file alone — always `false`, because a
 * refresh never deletes, and reported so the guarantee is checkable rather than assumed. The handler
 * built its body without it, so the decoder had no reason to declare it either.
 */
export const SyncDiagramToModelResultSchema = Schema.Struct({
  ...WriteResultSchema.fields,
  removed_entity_ids: Schema.Array(Schema.String),
  removed_connection_ids: Schema.Array(Schema.String),
  deleted_diagram: Schema.Boolean,
})
export type SyncDiagramToModelResult = typeof SyncDiagramToModelResultSchema.Type
