import type { Ref } from 'vue'
import type { GraphNode, LayoutMode } from './useForceGraph'
import type { BandPlacement } from './useForceGraphLayout'
import { domainBandPlacement, hopDepthByParentage } from '../views/GraphExploreView.helpers'

/**
 * Which arrangement each layout mode means, for free exploration.
 *
 * One answer to that question, in one place. It is asked from several directions — the toolbar
 * switching mode, an expansion folding in a new hop, a collapse removing one, a spacing preset
 * changing the forces — and every caller that answered it for itself was a copy that had to be
 * found again when a mode was added. Radial was added long after force and cluster, which is
 * exactly when the copies showed.
 *
 * The counterpart for viewpoint executions is `useExplorationLayout`: a fixed server-computed
 * population, with its own anchors and its own notion of what layout is current. These stay
 * apart for the same reason their loaders do.
 */

//: Ring spacing for the radial layout, in layout units.
const RADIAL_RING_SPACING = 180

/** Layout modes a free-exploration surface offers, in the order they are offered.
 *
 * Radial belongs here because the walk always has an anchor — the entity it opened on — for its
 * rings to be centred on, and it leads because it is what the surface opens in: hop distance from
 * the element you asked about is the thing a walk is actually reading, and a force layout of a
 * complete edge set stops separating anything once the graph is dense. */
export const FREE_LAYOUT_MODES: readonly { value: LayoutMode; label: string }[] = [
  { value: 'radial', label: 'Radial' },
  { value: 'cluster', label: 'Cluster' },
  { value: 'force', label: 'Force' },
]

export interface FreeExplorationLayoutDeps {
  nodes: Ref<GraphNode[]>
  rootId: Ref<string>
  layoutMode: Ref<LayoutMode>
  applyGroupClusterLayout: (
    groupOf: (id: string) => string,
    banding?: { placementOf: (k: string) => BandPlacement; anchorIds?: ReadonlySet<string> },
    onFrame?: () => void,
  ) => void
  applyRadialLayout: (distances: ReadonlyMap<string, number>, ringSpacing: number) => unknown
  /** Cool the force layout to rest visibly, calling back on every frame of the motion. */
  animateForceLayout: (onFrame?: () => void) => void
  /**
   * Frame the current positions unconditionally, discarding any framing the user had set.
   *
   * Called once at the start of a deliberate rearrangement. Expanding or collapsing changes
   * what there is to look at, so it is entitled to re-frame — a walk that kept a zoom from
   * three hops ago would put its new neighbours off-screen.
   */
  fitToView: () => void
  /**
   * Frame the current positions *unless the user has framed them since*.
   *
   * Called on every frame of a move. The distinction from `fitToView` is the whole of the
   * rule: the rearrangement claims the framing when it begins, and the user takes it back the
   * moment they touch the wheel — at which point the rest of the animation leaves them alone
   * instead of overwriting the viewBox sixty times a second.
   */
  keepFramed: () => void
}

export function useFreeExplorationLayout(deps: FreeExplorationLayoutDeps) {
  const {
    nodes, rootId, layoutMode,
    applyGroupClusterLayout, applyRadialLayout, animateForceLayout, fitToView, keepFramed,
  } = deps

  /**
   * Cluster mode: the same banded, wrapped layout the viewpoint surface uses, grouped by
   * domain and anchored on the node in question.
   *
   * Fit, not settle: the banded positions this computes ARE the layout, and settling would run
   * the force simulation over them and scatter the bands. Fitting on every frame of the move
   * rather than once at the end, because an expansion usually grows the graph past the current
   * frame, so a single fit afterwards plays most of the motion off-screen.
   */
  const applyDomainClusterLayout = (centerId?: string): void => {
    applyGroupClusterLayout(
      (id) => nodes.value.find((n) => n.id === id)?.domain || 'unknown',
      { placementOf: domainBandPlacement, anchorIds: new Set([centerId ?? rootId.value]) },
      keepFramed,
    )
  }

  /** Radial mode: ring the walk around the entity it opened on, by hop distance from it. */
  const applyHopRadialLayout = (): void => {
    applyRadialLayout(hopDepthByParentage(nodes.value, rootId.value), RADIAL_RING_SPACING)
    keepFramed()
  }

  /**
   * Re-apply whichever layout is current — what every structural change needs.
   *
   * The framing is reclaimed first: expanding, collapsing or changing the spacing changes what
   * there is to look at, and the new arrangement is entitled to be shown in full. From that
   * point the per-frame callback defers to the user, so a zoom *during* the move survives it.
   */
  const relayout = (centerId?: string): void => {
    fitToView()
    if (layoutMode.value === 'cluster') applyDomainClusterLayout(centerId)
    else if (layoutMode.value === 'radial') applyHopRadialLayout()
    // Force is animated rather than settled: switching to it is a rearrangement the user asked
    // for, so let them watch it happen. It used to start the loop and then immediately settle
    // it synchronously, which is two answers to one question.
    else animateForceLayout(keepFramed)
  }

  const switchLayout = (mode: LayoutMode): void => {
    layoutMode.value = mode
    relayout()
  }

  return { applyDomainClusterLayout, relayout, switchLayout }
}
