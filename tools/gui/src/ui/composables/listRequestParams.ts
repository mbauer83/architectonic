import type { Tier, TierSelection } from '../lib/tierUrlState'
import { scopeForTier, tierAllowsEngagementCollections } from '../lib/tierUrlState'

/**
 * Pure facet→fetch mappings for the list surfaces, one per surface, so the
 * tier↔scope translation each view sends to the API is testable without
 * mounting the views.
 */

export const documentListParams = (
  tier: TierSelection,
  docType: string,
): { doc_type?: string; scope?: string } => {
  const scope = scopeForTier(tier)
  return {
    ...(docType ? { doc_type: docType } : {}),
    ...(scope ? { scope } : {}),
  }
}

export const diagramListParams = (tier: TierSelection): { scope?: string } => {
  const scope = scopeForTier(tier)
  return scope ? { scope } : {}
}

/** Entities: an active engagement collection forces engagement scope (collections
 * exist only there); otherwise the tier facet decides. */
export const entityListScope = (
  tier: TierSelection,
  isGroupView: boolean,
): 'global' | 'engagement' | undefined => (isGroupView ? 'engagement' : scopeForTier(tier))

/** The saved collection preference merges into the URL only when no group is
 * selected and the tier allows engagement collections — never a redirect. */
export const savedGroupToMerge = (
  currentGroup: string,
  tier: TierSelection,
  saved: string | null,
): string | null => (!currentGroup && tierAllowsEngagementCollections(tier) && saved ? saved : null)

/** Viewpoint catalog filter value ↔ tier selection ('' means All). */
export const viewpointFilterFromTier = (tier: TierSelection): Tier | '' => (tier === 'all' ? '' : tier)
export const tierFromViewpointFilter = (value: Tier | ''): TierSelection => (value === '' ? 'all' : value)
