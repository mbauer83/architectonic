import type { LocationQuery, LocationQueryRaw } from 'vue-router'

/**
 * URL = state for the repository-tier facet. `?tier=` holds the selected tier;
 * All is the ABSENCE of the key. Each list surface passes its own allowed set
 * (viewpoints additionally allow `module`); absent, array, or disallowed values
 * decode to All and are normalized out of the URL via one router.replace that
 * preserves every unrelated query key and the hash.
 */

export type Tier = 'engagement' | 'enterprise' | 'module'
export type TierSelection = Tier | 'all'
export type AllowedTierSet = readonly Tier[]

export const LIST_TIERS: AllowedTierSet = ['engagement', 'enterprise'] as const
export const VIEWPOINT_TIERS: AllowedTierSet = ['engagement', 'enterprise', 'module'] as const

const isAllowed = (raw: string, allowed: AllowedTierSet): raw is Tier =>
  (allowed as readonly string[]).includes(raw)

/** Decode `?tier=` against the surface's allowed set. */
export const decodeTier = (query: LocationQuery, allowed: AllowedTierSet): TierSelection => {
  const raw = query.tier
  if (typeof raw !== 'string') return 'all'
  return isAllowed(raw, allowed) ? raw : 'all'
}

/** True when a `tier` key is present but not in canonical form for this surface
 * (array value, empty, or disallowed) — the surface then replaces the URL with
 * the normalized (All) form. An absent key is already canonical. */
export const tierNeedsNormalization = (query: LocationQuery, allowed: AllowedTierSet): boolean => {
  const raw = query.tier
  if (raw === undefined) return false
  return typeof raw !== 'string' || !isAllowed(raw, allowed)
}

/** The query with `tier` set (or removed for All), preserving unrelated keys. */
export const withTier = (query: LocationQuery, tier: TierSelection): LocationQueryRaw => {
  const merged: LocationQueryRaw = { ...query }
  delete merged.tier
  if (tier !== 'all') merged.tier = tier
  return merged
}

/** API `scope` param for a tier selection — the API keeps `scope=global` as its
 * internal identifier for the enterprise tier; All sends no scope. */
export const scopeForTier = (tier: TierSelection): 'global' | 'engagement' | undefined => {
  if (tier === 'enterprise') return 'global'
  return tier === 'engagement' ? 'engagement' : undefined
}

/** Engagement collections (groups) exist only outside the Enterprise tier. */
export const tierAllowsEngagementCollections = (tier: TierSelection): boolean => tier !== 'enterprise'
