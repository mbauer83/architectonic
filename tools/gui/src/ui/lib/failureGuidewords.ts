/**
 * The guidewords a component's function is analysed against — the frontend's single copy.
 *
 * Mirrors `src/domain/assurance/failure_modes.py`, which owns the vocabulary: the attribute-schema enum, the
 * matrix columns and the authoring guidance all derive from it there. Kept in step by
 * `tests/tools/test_failure_guideword_vocabulary_parity.py`, so a guideword cannot be added on one
 * side only — the failure mode this repository has already had once, when a divergent vocabulary
 * was accepted by a store column with no enum constraint and then silently dropped by the surface
 * that did not recognise it.
 *
 * Deliberately parallel to the five STPA guidewords: one set asks how a *control action* can be
 * unsafe, this one asks how a *component* can fail. Reading them side by side is how the two
 * methods become learnable together — while remembering that neither set covers the other's
 * ground.
 */

export interface FailureGuideword {
  /** Persisted value of a failure mode's `failure_type`. */
  slug: string
  /** Reader-facing column heading. */
  label: string
}

export const FAILURE_GUIDEWORDS: readonly FailureGuideword[] = [
  { slug: 'no-function', label: 'No function' },
  { slug: 'partial-function', label: 'Partial or degraded function' },
  { slug: 'excessive-function', label: 'Excessive function' },
  { slug: 'intermittent-function', label: 'Intermittent function' },
  { slug: 'unintended-function', label: 'Unintended function' },
] as const

export const FAILURE_GUIDEWORD_SLUGS: readonly string[] = FAILURE_GUIDEWORDS.map((g) => g.slug)

/** The heading for a guideword slug, falling back to the slug when unrecognised. */
export const failureGuidewordLabel = (slug: string): string =>
  FAILURE_GUIDEWORDS.find((g) => g.slug === slug)?.label ?? slug
