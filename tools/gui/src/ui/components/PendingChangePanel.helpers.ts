import type { ChangeSummary } from '../../domain/schemas/changes'

/**
 * The changes against one artifact, addressed however the caller happens to hold it.
 *
 * Both ids are accepted because both name the same artifact from different sides: a reader opening
 * this repository's reference holds the reference id, and one reading the promoted artifact directly
 * — the admin deployment — holds the enterprise id. Matching only one would leave the panel blank on
 * whichever deployment held the other.
 */
export const changesAgainst = (
  changes: readonly ChangeSummary[],
  artifactId: string,
): readonly ChangeSummary[] =>
  changes.filter((change) =>
    change.reference_id === artifactId || change.target_id === artifactId)
