import { ref, reactive, onUnmounted } from 'vue'
import {
  buildClusterBoxes, buildTree, layoutBandedClusters, layoutGroupClusters, layoutRadialByDistance, layoutTree,
  type BandPlacement,
} from './useForceGraphLayout'
import {
  ALPHA_HOT, COOLING_TICKS, FORCE_DEFAULTS, STEPS_PER_FRAME, coolerAlpha, isCold, simulationStep,
  type ForceOptions,
} from './forceSimulation'

export type { ForceOptions }

export type LayoutMode = 'force' | 'cluster' | 'radial'

export interface GraphNode {
  id: string
  label: string
  type: string // artifact_type prefix e.g. "GOL", "APP"
  artifactType?: string // full artifact type e.g. "goal" (resolved from the entity fetch)
  domain?: string
  x: number
  y: number
  vx: number
  vy: number
  expanded: boolean
  pinned: boolean
  totalConns?: number   // sum of conn_in + conn_sym + conn_out; undefined = not yet loaded
  addedBy?: string      // id of the node whose expansion added this node
}

export interface GraphEdge {
  source: string
  target: string
  connType: string
  description?: string  // raw content_text from the connection
  srcMultiplicity?: string
  tgtMultiplicity?: string
}

export function useForceGraph(width: () => number, height: () => number) {
  const nodes = ref<GraphNode[]>([])
  const edges = ref<GraphEdge[]>([])
  const options = reactive<ForceOptions>({ ...FORCE_DEFAULTS })
  const layoutMode = ref<LayoutMode>('force')
  let animId: number | null = null
  let running = false

  const addNode = (node: Omit<GraphNode, 'x' | 'y' | 'vx' | 'vy' | 'expanded' | 'pinned'>) => {
    if (nodes.value.some((n) => n.id === node.id)) return
    const parent = node.addedBy ? nodes.value.find((n) => n.id === node.addedBy) : null
    const ox = parent ? parent.x : width() / 2
    const oy = parent ? parent.y : height() / 2
    const angle = Math.random() * Math.PI * 2
    const dist = options.idealDist * (0.8 + Math.random() * 0.5)
    nodes.value.push({
      ...node,
      x: ox + Math.cos(angle) * dist,
      y: oy + Math.sin(angle) * dist,
      vx: 0, vy: 0,
      expanded: false, pinned: false,
    })
  }

  /** Distribute nodes added by expanding `parentId` in an arc pointing away from the grandparent.
   *  Root expansions use a full ring; all others use a 160° arc on the far side. */
  const spreadAroundParent = (parentId: string) => {
    const parent = nodes.value.find((n) => n.id === parentId)
    const children = nodes.value.filter((n) => n.addedBy === parentId)
    if (!parent || children.length === 0) return

    const grandparent = parent.addedBy ? nodes.value.find((n) => n.id === parent.addedBy) : null
    const awayAngle = grandparent
      ? Math.atan2(parent.y - grandparent.y, parent.x - grandparent.x)
      : Math.atan2(parent.y - height() / 2, parent.x - width() / 2)

    const dist = options.idealDist * 1.1
    const isRoot = !grandparent
    const halfSpread = isRoot ? Math.PI : Math.PI * 0.8
    children.forEach((n, i) => {
      const t = children.length > 1 ? i / (children.length - 1) - 0.5 : 0
      const angle = awayAngle + halfSpread * 2 * t
      n.x = parent.x + Math.cos(angle) * dist
      n.y = parent.y + Math.sin(angle) * dist
      n.vx = Math.cos(angle) * 5
      n.vy = Math.sin(angle) * 5
    })
  }

  const addEdge = (edge: GraphEdge) => {
    const exists = edges.value.some(
      (e) => e.source === edge.source && e.target === edge.target && e.connType === edge.connType,
    )
    if (!exists) edges.value.push({ ...edge })
  }

  const markExpanded = (id: string) => {
    const n = nodes.value.find((n) => n.id === id)
    if (n) n.expanded = true
  }

  //: Current temperature of the run. Reset to hot whenever the graph is asked to move again.
  let alpha = ALPHA_HOT

  /** One cooled step. False once the run is over — either cold, or already at rest. */
  const stepCooling = (): boolean => {
    const moving = simulationStep(
      nodes.value, edges.value, options, { x: width() / 2, y: height() / 2 }, alpha,
    )
    alpha = coolerAlpha(alpha)
    return moving && !isCold(alpha)
  }

  const coolToRest = () => {
    for (let i = 0; i < COOLING_TICKS && stepCooling(); i++) { /* cool to rest */ }
  }

  const stop = () => {
    running = false
    if (animId !== null) { cancelAnimationFrame(animId); animId = null }
  }

  /**
   * Cool the simulation to rest across real frames.
   *
   * `onFrame` runs after each step so the caller can keep the view framed while the graph
   * moves, rather than snapping to its new bounds once at the end. That is deliberately the
   * same contract `tweenTo` offers: the two animations on this surface are driven the same
   * way, so they cannot drift apart the way two descriptions of one geometry once did.
   *
   * Synchronous when there is no frame clock — a test runner, a headless render, anything
   * that is not a browser paint loop. The resting arrangement is the contract and the motion
   * is presentation, so land on it at once rather than freezing on frame one.
   */
  const runCooling = (onFrame?: () => void): void => {
    stop()
    alpha = ALPHA_HOT
    if (typeof requestAnimationFrame !== 'function') {
      coolToRest()
      onFrame?.()
      return
    }
    running = true
    const loop = () => {
      if (!running) return
      // Several steps per painted frame: the schedule is a step budget, and spending it one
      // step per frame made the animation long *and* still ended short of the arrangement the
      // forces describe. See `STEPS_PER_FRAME`.
      let active = true
      for (let step = 0; step < STEPS_PER_FRAME && active; step++) active = stepCooling()
      onFrame?.()
      if (active) { animId = requestAnimationFrame(loop) } else { running = false; animId = null }
    }
    animId = requestAnimationFrame(loop)
  }

  const start = () => runCooling()
  const restart = () => runCooling()

  //: Duration of a cluster relayout. Long enough to be followed by eye, short enough that a
  //: run of expansions does not feel slow.
  const TWEEN_MS = 320
  let tweenId: number | null = null

  const cancelTween = () => {
    if (tweenId !== null && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(tweenId)
    tweenId = null
  }

  /**
   * Ease every node from where it is to where the layout says it belongs.
   *
   * Cluster layouts compute final positions and used to assign them outright, so expanding a
   * node teleported the entire graph — the reader had no way to see which nodes were new or
   * where the ones they were watching went. The force layout has always animated; this gives
   * the deterministic layouts the same continuity without giving them a simulation.
   *
   * `onFrame` runs after each step so the caller can keep the view framed while the graph
   * grows into its new bounds, rather than snapping to them once at the end.
   */
  const tweenTo = (posMap: ReadonlyMap<string, { x: number; y: number }>, onFrame?: () => void): void => {
    cancelTween()
    const legs = nodes.value.map((n) => ({ node: n, x0: n.x, y0: n.y, target: posMap.get(n.id) }))
    if (legs.every((leg) => leg.target === undefined)) return

    const settle = (eased: number) => {
      for (const leg of legs) {
        if (!leg.target) continue
        leg.node.x = leg.x0 + (leg.target.x - leg.x0) * eased
        leg.node.y = leg.y0 + (leg.target.y - leg.y0) * eased
        leg.node.vx = 0; leg.node.vy = 0
      }
      onFrame?.()
    }

    // No frame clock — a test runner, a headless render, anything that is not a browser
    // paint loop. The animation is presentation; the layout is the contract, so land on it
    // at once rather than freezing on the first frame of a tween that will never advance.
    if (typeof requestAnimationFrame !== 'function') {
      settle(1)
      return
    }

    const began = performance.now()
    const step = () => {
      const elapsed = Math.min(1, (performance.now() - began) / TWEEN_MS)
      settle(1 - (1 - elapsed) ** 3) // ease-out cubic: quick departure, gentle arrival
      tweenId = elapsed < 1 ? requestAnimationFrame(step) : null
    }
    step()
  }

  /** Run the cooling schedule synchronously, leaving the graph STOPPED — a freshly rendered
   * fixed population is immediately hit-testable, with nothing drifting away under the
   * pointer. Viewpoint executions (fixed result sets) settle before first paint; incremental
   * free exploration animates instead, via `animateForceLayout`. Both cool identically, so
   * they come to rest in the same arrangement. */
  const settleForceLayout = () => {
    layoutMode.value = 'force'
    stop()
    alpha = ALPHA_HOT
    coolToRest()
  }

  /** Cool the force layout to rest visibly, reporting each frame to `onFrame`.
   *
   * The animated counterpart of `settleForceLayout`, for the case where the population just
   * grew under the user: expansion is the one moment the graph should move, and a move that
   * happens between two paints reads as the graph vanishing and coming back rearranged. */
  const animateForceLayout = (onFrame?: () => void) => {
    layoutMode.value = 'force'
    runCooling(onFrame)
  }

  // ── Cluster / dendrogram layout (helpers live in useForceGraphLayout.ts) ──

  const applyClusterLayout = (rootId: string, centerId?: string): { cx?: number; cy?: number } => {
    stop()
    layoutMode.value = 'cluster'
    if (nodes.value.length === 0) return {}
    const tree = buildTree(edges.value, rootId)
    const { posMap, cx: canvasWidth, cy: canvasHeight } = layoutTree(nodes.value, tree, width(), height())
    for (const nd of nodes.value) {
      const pos = posMap.get(nd.id)
      if (pos) { nd.x = pos.x; nd.y = pos.y }
      nd.vx = 0; nd.vy = 0
    }
    const target = centerId ?? rootId
    const pos = posMap.get(target)
    return pos ? { cx: Math.min(Math.max(pos.x, 0), canvasWidth), cy: Math.min(Math.max(pos.y, 0), canvasHeight) } : {}
  }

  /** Positions the current node set into clusters by `groupOf(id)` — the viewpoint
   *  exploration mode's `group_by`-driven layout: no root/expand adjacency is assumed,
   *  unlike `applyClusterLayout`, so groups are packed as 2D boxes rather than laid out by
   *  tree depth. */
  const applyGroupClusterLayout = (
    groupOf: (id: string) => string,
    banding?: { placementOf: (groupKey: string) => BandPlacement; anchorIds?: ReadonlySet<string> },
    onFrame?: () => void,
  ): void => {
    stop()
    layoutMode.value = 'cluster'
    if (nodes.value.length === 0) return
    const boxes = buildClusterBoxes(nodes.value, groupOf, banding?.anchorIds ?? new Set())
    // Banded only when the caller supplies an ordering for its own group vocabulary. This
    // composable serves every graph surface, so it has no basis for inventing one.
    const { posMap } = banding
      ? layoutBandedClusters(boxes, width(), height(), banding.placementOf, banding.anchorIds ?? new Set())
      : layoutGroupClusters(boxes, width(), height())
    tweenTo(posMap, onFrame)
  }

  /** Positions the current node set on concentric rings by hop distance from an anchored
   *  execution's anchors (`layoutRadialByDistance`) — anchors at the canvas centre, more
   *  distant nodes on farther rings. Returns the ring centre so callers can pan onto it. */
  const applyRadialLayout = (distances: ReadonlyMap<string, number>, ringSpacing: number): { cx: number; cy: number } => {
    stop()
    layoutMode.value = 'radial'
    const center = { x: width() / 2, y: height() / 2 }
    if (nodes.value.length === 0) return { cx: center.x, cy: center.y }
    const posMap = layoutRadialByDistance(nodes.value, distances, center, ringSpacing)
    for (const nd of nodes.value) {
      const pos = posMap.get(nd.id)
      if (pos) { nd.x = pos.x; nd.y = pos.y }
      nd.vx = 0; nd.vy = 0
    }
    return { cx: center.x, cy: center.y }
  }

  /** Remove a node and all nodes that were added exclusively by its expansion. */
  const collapseNode = (id: string) => {
    const toRemove = new Set<string>()
    const collect = (nodeId: string) => {
      for (const n of nodes.value) {
        if (n.addedBy === nodeId && !toRemove.has(n.id)) {
          toRemove.add(n.id)
          collect(n.id)
        }
      }
    }
    collect(id)
    // Only remove a node if ALL its edges connect to either the collapsed subtree or the source
    const retained = nodes.value.filter((n) => !toRemove.has(n.id)).map((n) => n.id)
    const retainedSet = new Set(retained)
    const safeToRemove = new Set<string>()
    for (const rid of toRemove) {
      const hasOutsideEdge = edges.value.some((e) =>
        (e.source === rid || e.target === rid) &&
        retainedSet.has(e.source === rid ? e.target : e.source) &&
        e.source !== id && e.target !== id,
      )
      if (!hasOutsideEdge) safeToRemove.add(rid)
    }
    if (safeToRemove.size === 0) return
    nodes.value = nodes.value.filter((n) => !safeToRemove.has(n.id))
    edges.value = edges.value.filter(
      (e) => !safeToRemove.has(e.source) && !safeToRemove.has(e.target),
    )
    const collapsed = nodes.value.find((n) => n.id === id)
    if (collapsed) collapsed.expanded = false
  }

  const applyForceLayout = () => {
    layoutMode.value = 'force'
    runCooling()
  }

  onUnmounted(() => { stop(); cancelTween() })

  return {
    nodes, edges, options, layoutMode,
    addNode, addEdge, markExpanded, collapseNode, spreadAroundParent,
    start, stop, restart, settleForceLayout, animateForceLayout,
    applyClusterLayout, applyGroupClusterLayout, applyRadialLayout, applyForceLayout,
  }
}
