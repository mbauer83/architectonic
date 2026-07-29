import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  decodeTier,
  tierNeedsNormalization,
  withTier,
  type AllowedTierSet,
  type TierSelection,
} from '../lib/tierUrlState'

/**
 * URL-backed tier facet for one list surface.
 *
 * Decodes `?tier=` against the surface's allowed set; invalid values (array,
 * empty, disallowed) are normalized to All via ONE router.replace that spreads
 * the existing `route.query` (owned key only: `tier`) and preserves the hash.
 * Facet changes write through the same merge, so adjacent filters and deep-link
 * fragments survive tier switches.
 */
export function useTierFacet(allowed: AllowedTierSet) {
  const route = useRoute()
  const router = useRouter()

  const tier = computed<TierSelection>(() => decodeTier(route.query, allowed))

  watch(
    () => route.query.tier,
    () => {
      if (tierNeedsNormalization(route.query, allowed)) {
        void router.replace({ query: withTier(route.query, 'all'), hash: route.hash })
      }
    },
    { immediate: true },
  )

  const setTier = (value: TierSelection): void => {
    void router.replace({ query: withTier(route.query, value), hash: route.hash })
  }

  return { tier, setTier }
}
