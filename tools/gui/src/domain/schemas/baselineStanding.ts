import { Schema } from 'effect'

/**
 * How an artifact stands relative to the enterprise baseline.
 *
 * An engagement repository reads enterprise artifacts through references and cannot write them, so a
 * change to one is *proposed* and lives locally until it is accepted upstream. Every artifact row the
 * backend serves says which of the two it is showing.
 *
 * Two arms discriminated on `kind`, matching the server's own closed union, so a view matches
 * exhaustively instead of inferring the case from which fields happen to be present.
 *
 * **Required, never optional.** `is_global` sits beside this on the same rows declared
 * `bool | None = None`, and two of its three server-side serialisers omit it — so a reader cannot
 * tell "not global" from "nobody said". Here that distinction *is* the answer: a missing value would
 * read as the baseline, showing a proposed artifact as accepted upstream.
 */
export const EnterpriseBaselineSchema = Schema.Struct({
  kind: Schema.Literal('enterprise-baseline'),
})

export const ProposedStandingSchema = Schema.Struct({
  kind: Schema.Literal('proposed'),
  /** Every live change against this artifact, so a reader can open them. */
  proposal_ids: Schema.Array(Schema.String),
  /** Which parts differ — the question a boolean could not answer. */
  changed_fields: Schema.Array(Schema.String),
  /** What the artifact was when the changes were written. */
  base_revision: Schema.String,
  /** Derived on read, never stored: whether the changes still apply to the baseline they name. */
  condition: Schema.Literal('current', 'stale', 'conflicting'),
  /**
   * Whether anyone upstream has been asked to look yet — `awaiting-review` as soon as *one* of
   * the changes has been sent, because that is when taking one back stops being private.
   */
  review: Schema.Literal('not-sent', 'awaiting-review'),
})

export const BaselineStandingSchema = Schema.Union(EnterpriseBaselineSchema, ProposedStandingSchema)

export type BaselineStanding = typeof BaselineStandingSchema.Type
export type ProposedStanding = typeof ProposedStandingSchema.Type

/** Whether this standing carries local changes — the one predicate most views need. */
export const isProposed = (standing: BaselineStanding): standing is ProposedStanding =>
  standing.kind === 'proposed'
