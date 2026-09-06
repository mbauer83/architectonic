import type { ChangeSummary } from '../../domain/schemas/changes'

/**
 * The changes against one artifact, named the way a reader holds it: the promoted artifact's own id.
 *
 * Not the reference's. A reference is machinery, kept out of every list and every search, so no page
 * a reader can reach is addressed by one — and a panel matching on it would be a second place that
 * had to know references exist.
 */
export const changesAgainst = (
  changes: readonly ChangeSummary[],
  artifactId: string,
): readonly ChangeSummary[] =>
  changes.filter((change) => change.target_id === artifactId)
