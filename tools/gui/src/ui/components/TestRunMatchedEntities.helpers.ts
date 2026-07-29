import type { EntityItemSummary } from '../../domain'

/** Display cap for the Test-run matched-entity list — enough to name what matched
 * without turning the panel into a full result surface. */
export const MATCHED_DISPLAY_CAP = 50

export const cappedMatches = (
  entities: readonly EntityItemSummary[],
): readonly EntityItemSummary[] => entities.slice(0, MATCHED_DISPLAY_CAP)

export const hiddenMatchCount = (entities: readonly EntityItemSummary[], totalCount: number): number =>
  Math.max(0, totalCount - cappedMatches(entities).length)

/** Provenance tag for an entity whose criteria match rested on derived-relationship
 * evidence; null when the match holds on modeled facts alone. */
export const derivedMatchTag = (entity: EntityItemSummary): string | null =>
  entity.matched_via_derived_hops != null
    ? `matched via derived (${entity.matched_via_derived_hops} hops)`
    : null
