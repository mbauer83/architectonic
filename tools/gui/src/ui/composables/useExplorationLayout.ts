import { computed, ref, type Ref } from 'vue'
import type { PresentationNode } from '../../domain/viewpointPresentation'
import type { ViewpointExecutionResult } from '../../domain'
import {
  anchorDistancesFromResult, domainBandPlacement, effectiveExplorationLayout, groupKeyFor, isDomainGrouping,
  type ExplorationLayoutOverride,
} from '../views/GraphExploreView.helpers'
import type { BandPlacement } from './useForceGraphLayout'

interface ExplorationLayoutActions {
  applyRadialLayout: (distances: ReadonlyMap<string, number>, ringSpacing: number) => { cx: number; cy: number }
  settleForceLayout: () => void
  applyGroupClusterLayout: (
    groupOf: (id: string) => string,
    banding?: { placementOf: (groupKey: string) => BandPlacement; anchorIds?: ReadonlySet<string> },
  ) => void
  fitToView: () => void
}

const RADIAL_RING_SPACING = 180

/**
 * Anchored-exploration geometry for a viewpoint result: hop distances from the anchor,
 * the anchor-membership test, and the layout the exploration surface applies for the
 * current execution (explicit override → declared `display_options.layout` → anchored
 * radial / unanchored group-cluster default). Layout mutation is delegated to the graph
 * actions so this composable stays free of force-simulation state.
 */
export function useExplorationLayout(
  result: Ref<ViewpointExecutionResult | null>,
  presentation: Ref<PresentationNode | null>,
  actions: ExplorationLayoutActions,
) {
  const anchorIds = computed(() => result.value?.anchor_ids ?? [])
  const isAnchor = (id: string) => anchorIds.value.includes(id)
  const hopDepthById = computed(() => {
    const value = result.value
    if (!value || value.anchor_ids.length === 0) return new Map<string, number>()
    return anchorDistancesFromResult(value.entities)
  })
  const maxHopDepth = computed(() => Math.max(0, ...hopDepthById.value.values()))
  const hasUnrankedNodes = computed(() =>
    (result.value?.entities ?? []).some((e) => e.anchor_modeled_distance == null),
  )

  const layoutOverride = ref<ExplorationLayoutOverride>('auto')
  const applyExplorationLayout = () => {
    const value = result.value
    if (!value) return
    const layout = effectiveExplorationLayout(
      layoutOverride.value, presentation.value?.displayOptions['layout'], value.anchor_ids.length > 0,
    )
    if (layout === 'radial') {
      actions.applyRadialLayout(hopDepthById.value, RADIAL_RING_SPACING)
      actions.fitToView()
      return
    }
    if (layout === 'force') {
      // Fixed result population: settle synchronously so nodes are immediately
      // hit-testable — nothing drifts away under the pointer.
      actions.settleForceLayout()
      actions.fitToView()
      return
    }
    const groupBy = presentation.value?.groupBy ?? null
    const byId = new Map(value.entities.map((e) => [e.id, e]))
    const keyOf = (id: string) => {
      const entity = byId.get(id)
      return entity ? groupKeyFor(entity, groupBy) : 'other'
    }
    // Grouped by domain the keys carry the ontology's layer ordering, so position can mean
    // something; grouped by anything else there is no such ordering to honour.
    const keys = value.entities.map((e) => keyOf(e.id))
    actions.applyGroupClusterLayout(
      keyOf,
      isDomainGrouping(keys)
        ? { placementOf: domainBandPlacement, anchorIds: new Set(value.anchor_ids) }
        : undefined,
    )
    actions.fitToView()
  }

  const setExplorationLayout = (choice: ExplorationLayoutOverride) => {
    layoutOverride.value = choice
    applyExplorationLayout()
  }

  return {
    anchorIds, isAnchor, hopDepthById, maxHopDepth, hasUnrankedNodes,
    layoutOverride, applyExplorationLayout, setExplorationLayout,
  }
}
