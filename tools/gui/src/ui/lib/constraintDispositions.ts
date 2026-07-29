/**
 * How an assurance constraint has been dealt with — the frontend's single copy.
 *
 * Mirrors `src/domain/assurance/constraint_dispositions.py`, which owns the vocabulary: the
 * attribute-schema enum, the write-boundary validation and the safety-subordination
 * safeguard all derive from it there. Kept in step by
 * `tests/tools/test_constraint_disposition_vocabulary_parity.py`, so a value cannot be
 * added on one side only.
 *
 * The order is the hierarchy of controls, strongest first — a preference ranking, not a
 * magnitude. `mitigate`, `transfer` and `avoid` are absent by decision: they are ISO 31000
 * risk treatment and belong to a risk's `treatment`. So is `open`: "no strategy decided
 * yet" is the empty field, so every listed value is something somebody chose.
 */

export interface ConstraintDisposition {
  /** Persisted value of a constraint's `disposition`. */
  slug: string
  /** Reader-facing wording. */
  label: string
}

export const CONSTRAINT_DISPOSITIONS: readonly ConstraintDisposition[] = [
  { slug: 'eliminated', label: 'Eliminated' },
  { slug: 'prevented-by-design', label: 'Prevented by design' },
  { slug: 'controlled-with-evidence', label: 'Controlled with evidence' },
  { slug: 'alarp-justified', label: 'ALARP-justified' },
  { slug: 'accepted', label: 'Accepted' },
] as const

export const CONSTRAINT_DISPOSITION_SLUGS: readonly string[] = CONSTRAINT_DISPOSITIONS.map((d) => d.slug)

/** Reader-facing wording for a slug, or the slug itself when unrecognised. */
export function dispositionLabel(slug: string): string {
  return CONSTRAINT_DISPOSITIONS.find((d) => d.slug === slug)?.label ?? slug
}
