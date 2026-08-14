import { computed, watch, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  excludedCount,
  facetOptions,
  narrowed,
  type ClassificationLevels,
  type FacetableEdge,
  type FacetableNode,
  type FacetOptions,
  type FacetSelection,
} from '../lib/graphFacets'
import {
  decodeFacetSelection,
  facetSelectionNeedsNormalization,
  withFacetSelection,
  withValueToggled,
} from '../lib/graphFacetUrlState'

/**
 * URL-backed facet state for one graph surface.
 *
 * The same split `useTierFacet` established: the composable owns the router, the lib owns the
 * encoding, and the component owns none of it. Selection changes and normalization both go through
 * ONE `router.replace` that spreads `route.query` (owned key only: `hide`) and preserves the hash,
 * so the graph explorer's `?viewpoint=` and `?param.*` survive a filter change.
 *
 * The offered values are derived from the *loaded* graph, so they follow exploration: expanding a
 * node that brings in a new domain adds that domain to the facet without a fetch.
 */
export function useGraphFacets<N extends FacetableNode, E extends FacetableEdge>(input: {
  levels: Ref<ClassificationLevels | null>
  nodes: Ref<readonly N[]>
  edges: Ref<readonly E[]>
}) {
  const route = useRoute()
  const router = useRouter()

  const selection = computed<FacetSelection>(() => decodeFacetSelection(route.query))

  watch(
    () => route.query.hide,
    () => {
      if (facetSelectionNeedsNormalization(route.query)) {
        void router.replace({
          query: withFacetSelection(route.query, decodeFacetSelection(route.query)),
          hash: route.hash,
        })
      }
    },
    { immediate: true },
  )

  const entityFacets = computed<readonly FacetOptions[]>(() =>
    input.levels.value ? facetOptions(input.levels.value.entity, input.nodes.value) : [],
  )
  const relationFacets = computed<readonly FacetOptions[]>(() =>
    input.levels.value ? facetOptions(input.levels.value.relation, input.edges.value) : [],
  )

  /** What the canvas draws. Unfiltered, and before the levels arrive, this is the graph itself. */
  const visible = computed(() =>
    input.levels.value
      ? narrowed(input.levels.value, selection.value, input.nodes.value, input.edges.value)
      : { nodes: input.nodes.value, edges: input.edges.value },
  )

  /** What the collapsed headline reports. A filter that hides invisibly is B30's defect as a feature. */
  const excluded = computed(() => excludedCount(selection.value))

  const toggle = (level: string, value: string): void => {
    void router.replace({
      query: withFacetSelection(route.query, withValueToggled(selection.value, level, value)),
      hash: route.hash,
    })
  }

  const reset = (): void => {
    void router.replace({ query: withFacetSelection(route.query, {}), hash: route.hash })
  }

  return { selection, entityFacets, relationFacets, visible, excluded, toggle, reset }
}
