import type { AllowedTierSet, TierSelection } from '../lib/tierUrlState'
import { TIER_LABELS } from './TierBadge.helpers'

export interface TierFacetOption {
  readonly value: TierSelection
  readonly label: string
}

/** Segmented-control options for a surface: All first, then the surface's allowed
 * tiers in their declared order. */
export const tierFacetOptions = (allowed: AllowedTierSet): TierFacetOption[] => [
  { value: 'all', label: 'All' },
  ...allowed.map((tier) => ({ value: tier, label: TIER_LABELS[tier] })),
]
