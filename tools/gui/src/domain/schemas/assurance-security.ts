import { Schema } from 'effect'

/**
 * One architecture entity that carries an active security-signal snapshot, with how much it holds.
 *
 * Both counts are always sent. Zero components and zero findings is a real state — an ingest that ran
 * and found nothing — and distinguishing it from "no snapshot at all" is the whole reason an entity
 * appears in this list rather than being absent from it.
 */
export const AssessedEntitySchema = Schema.Struct({
  entity_id: Schema.String,
  snapshot_id: Schema.String,
  bom_component_count: Schema.Number,
  finding_count: Schema.Number,
})
export type AssessedEntity = typeof AssessedEntitySchema.Type

/**
 * Store-wide security-signal totals, and which entities have been assessed.
 *
 * `assessed_entities` is what makes the findings surface reachable without already knowing an anchor.
 * The per-anchor read is a subresource of the entity — `/api/assurance/arch-artifacts/{id}/
 * security-findings` — so a caller needs an id to ask at all, and the unanchored list address that
 * used to answer "every finding" is retired. This is the list that replaces it: the anchors, not the
 * findings, which is the honest shape now that a finding belongs to an entity.
 *
 * Every field is nullable because the response is also what a locked or ceiling-limited caller gets,
 * where `reason` carries why the numbers are absent rather than zero.
 */
export const SecuritySignalStatsSchema = Schema.Struct({
  total_snapshots: Schema.optional(Schema.NullOr(Schema.Number)),
  active_snapshots: Schema.optional(Schema.NullOr(Schema.Number)),
  assessed_entity_count: Schema.optional(Schema.NullOr(Schema.Number)),
  assessed_entities: Schema.optional(Schema.NullOr(Schema.Array(AssessedEntitySchema))),
  active_snapshot_bom_components: Schema.optional(Schema.NullOr(Schema.Number)),
  active_snapshot_findings: Schema.optional(Schema.NullOr(Schema.Number)),
  reason: Schema.optional(Schema.NullOr(Schema.String)),
})
export type SecuritySignalStats = typeof SecuritySignalStatsSchema.Type

export const decodeSecuritySignalStats = Schema.decodeUnknownSync(SecuritySignalStatsSchema)
