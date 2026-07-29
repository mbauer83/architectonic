/**
 * The STPA guidewords a control action is analysed against — the frontend's single copy.
 *
 * Mirrors `src/domain/assurance/uca_guidewords.py`, which owns the vocabulary: the attribute-schema enum, the
 * store migration, and the authoring guidance all derive from it there. Kept in step by
 * `tests/tools/test_uca_guideword_vocabulary_parity.py`, so a guideword cannot be added on one side
 * only.
 *
 * "Providing causes a hazard" is deliberately two guidewords. A command can be hazardous because
 * the **context** is wrong (well-formed, issued in a state where it must not be) or because the
 * **command** is wrong (issuing it is called for, its content is not). The first is answered by a
 * guard on state, the second by validating the command, so an analysis that cannot tell them apart
 * cannot say which constraint it needs. `wrong-duration` is the parallel of `wrong-timing`: both ask
 * about *when*, one about the instant and one about how long.
 */

export interface UcaGuideword {
  /** Persisted value of a UCA's `uca_type`. */
  slug: string
  /** Reader-facing column heading. */
  label: string
}

export const UCA_GUIDEWORDS: readonly UcaGuideword[] = [
  { slug: 'not-provided', label: 'Not provided' },
  { slug: 'provided-in-unsafe-context', label: 'Provided in unsafe context' },
  { slug: 'provided-incorrectly', label: 'Provided incorrectly' },
  { slug: 'wrong-timing', label: 'Wrong timing or order' },
  { slug: 'wrong-duration', label: 'Wrong duration' },
] as const

export const UCA_GUIDEWORD_SLUGS: readonly string[] = UCA_GUIDEWORDS.map((g) => g.slug)

/**
 * Guideword values that predate the current vocabulary, mapped to their current slug.
 *
 * Two sources: the split of `provided`, and a node-authoring form that offered
 * `commission | omission | wrong-timing | wrong-duration` — a set of its own. The store's
 * `uca_type` column has no enum constraint, so those values were accepted and then silently dropped
 * by the matrix, which only reads the columns it knows.
 *
 * The store migration rewrites persisted values, but a node read before an operator has upgraded —
 * or exported from an older store — can still carry one, and it must land in the right column
 * rather than in a stray one.
 */
const LEGACY_SLUGS: Readonly<Record<string, string>> = {
  'provided': 'provided-in-unsafe-context',
  'commission': 'provided-in-unsafe-context',
  'omission': 'not-provided',
  'stopped-too-soon': 'wrong-duration',
}

/** The current slug for a persisted `uca_type`; an unrecognised value is returned unchanged. */
export const canonicalGuideword = (slug: string | null | undefined): string =>
  slug ? (LEGACY_SLUGS[slug] ?? slug) : ''

/** The heading for a guideword slug, falling back to the slug when unrecognised. */
export const guidewordLabel = (slug: string): string => {
  const canonical = canonicalGuideword(slug)
  return UCA_GUIDEWORDS.find((g) => g.slug === canonical)?.label ?? slug
}
