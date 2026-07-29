import type { Tier } from '../lib/tierUrlState'

/** User-facing tier copy: always "Enterprise", never "Global"; the module tier
 * displays as "Built-in" (the URL and API keep the technical value `module`). */
export const TIER_LABELS: Record<Tier, string> = {
  engagement: 'Engagement',
  enterprise: 'Enterprise',
  module: 'Built-in',
}

/** Lowercase variant for inline/sentence contexts (select options, row tags). */
export const tierDisplayLowercase = (tier: Tier): string => TIER_LABELS[tier].toLowerCase()

/** The one accessibility label every tier badge carries. */
export const tierBadgeAriaLabel = (tier: Tier): string => `Repository tier: ${TIER_LABELS[tier]}`

/** Row badges derive their tier from the list contract's required `is_global` flag. */
export const tierFromIsGlobal = (isGlobal: boolean): Tier => (isGlobal ? 'enterprise' : 'engagement')
