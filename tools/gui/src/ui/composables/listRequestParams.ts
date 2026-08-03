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

/**
 * The `?group=` value meaning **every collection**, as distinct from an absent parameter.
 *
 * Absence means "no opinion", and the saved-preference merge below fills it in. A link that has
 * already decided the scope needs a way to say so, or it inherits a collection the caller never
 * chose — which is exactly what the Home page's domain cards did: their counts come from
 * `/api/stats`, documented as *repository-wide*, while the link they built carried no `group` and so
 * arrived narrowed to whatever collection was last browsed. The number promised one scope and the
 * destination showed another.
 */
export const ALL_GROUPS = 'all'

/** The collection a `?group=` value selects; `''` for every collection. */
export const groupFromQuery = (raw: string | undefined): string =>
  raw === undefined || raw === ALL_GROUPS ? '' : raw

/**
 * The entity-list query for a domain counted across the whole repository.
 *
 * A named builder rather than an inline literal because the scope is the part that gets forgotten:
 * `{ domain }` alone is a correct-looking link that arrives somewhere else. Any surface reporting a
 * repository-wide number — the Home page's domain cards today — should link through this, so the
 * scope its count was computed in is the scope its link opens.
 */
export const repositoryWideDomainQuery = (domain: string): { domain: string; group: string } =>
  ({ domain, group: ALL_GROUPS })

/**
 * The saved collection preference merges into the URL only when the caller expressed no scope at
 * all and the tier allows engagement collections — never a redirect.
 *
 * Takes the **raw** query value rather than the resolved collection, because those differ in the one
 * case that matters: `undefined` (no opinion, so restore what was last browsed) against `ALL_GROUPS`
 * (a decision, so leave it alone). Both resolve to `''` through `groupFromQuery`, which is why this
 * cannot be asked of the resolved value.
 *
 * The merge itself is deliberate and load-bearing elsewhere: `NavBar`'s browse link and
 * `EntityDetailView`'s back link both carry `domain`/`view`/`type` and drop `group`, and it is this
 * restore that keeps you inside the collection you were browsing when you follow them.
 */
export const savedGroupToMerge = (
  rawGroup: string | undefined,
  tier: TierSelection,
  saved: string | null,
): string | null =>
  rawGroup === undefined && tierAllowsEngagementCollections(tier) && saved ? saved : null

/** Viewpoint catalog filter value ↔ tier selection ('' means All). */
export const viewpointFilterFromTier = (tier: TierSelection): Tier | '' => (tier === 'all' ? '' : tier)
export const tierFromViewpointFilter = (value: Tier | ''): TierSelection => (value === '' ? 'all' : value)
