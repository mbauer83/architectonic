<script setup lang="ts">
/**
 * Assurance neighborhood explorer: renders the policy-filtered traversal from
 * GET /api/assurance/nodes/{node_id}/neighbors on the generic graph canvas. Double-click
 * expands a node with a fresh one-hop request (that is also how partial
 * results continue past a size budget — no continuation tokens). A locked
 * store collapses the whole panel and nothing further is fetched.
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import GraphCanvas from '../components/GraphCanvas.vue'
import GraphLayoutToolbar, { type LayoutModeOption } from '../components/GraphLayoutToolbar.vue'
import type { SpacingPreset } from '../composables/graphSpacingPresets'
import AssuranceNodeDetail from '../components/AssuranceNodeDetail.vue'
import {
  useForceGraph, type GraphNode, type GraphEdge, type LayoutMode,
} from '../composables/useForceGraph'
import type { NodeVisual, EdgeVisual } from '../components/GraphCanvas.helpers'
import {
  assuranceBandPlacement, assuranceNodeColor, clearsGraph, emptyPanelState, nodeTypeLabel,
  outcomeForResponse, panelStateForOutcome,
  type AssuranceGraphPanelState, type AssuranceNeighborsResponse,
} from './AssuranceGraphExploreView.helpers'

const route = useRoute()
// Absent on the unanchored exploration route, which opens on the whole visible graph.
const rootId = computed(() => (route.params.nodeId as string | undefined) ?? '')

const canvasRef = ref<InstanceType<typeof GraphCanvas> | null>(null)
const svgWidth = ref(800)
const svgHeight = ref(600)
const onCanvasResized = (width: number, height: number) => {
  svgWidth.value = width
  svgHeight.value = height
}

const {
  nodes, edges, options, layoutMode, addNode, addEdge, markExpanded, collapseNode,
  animateForceLayout, applyGroupClusterLayout, applyRadialLayout,
} = useForceGraph(() => svgWidth.value, () => svgHeight.value)

const panel = ref<AssuranceGraphPanelState>(emptyPanelState())
const loading = ref(true)  // a view that loads on mount is loading from its first frame, not after it
const nodeTypeById = ref(new Map<string, string>())
const selectedEdge = ref<GraphEdge | null>(null)

/** Hop distance from the node the exploration started at, kept across expansions so the
 *  ring a node sits on keeps meaning the same thing. A merged response reports hops from
 *  the node being expanded, so they are rebased onto that node's own distance. */
const hopById = ref(new Map<string, number>())

const RADIAL_RING_SPACING = 180
const ASSURANCE_LAYOUT_MODES: readonly LayoutModeOption[] = [
  { value: 'force', label: 'Force' },
  { value: 'cluster', label: 'Cluster' },
  { value: 'radial', label: 'Radial' },
]

const fitToView = () => { void nextTick(() => { canvasRef.value?.fitToView() }) }

/** Per-frame framing during an animated layout. A plain fit would run on every frame of the
 *  motion and overwrite the viewBox, undoing a wheel zoom on the very next frame. */
const keepFramed = () => { void nextTick(() => { canvasRef.value?.refitUnlessUserFramed() }) }

/**
 * Cluster mode: band by assurance node type, anchored on the node being explored.
 *
 * The band ordering is the assurance module's own (`assuranceBandPlacement`) and is injected
 * into the shared layout, exactly as the architecture explorer injects its domain ordering.
 * Fitting on every frame of the move rather than once at the end, because an expansion
 * usually grows the graph past the current frame.
 */
const applyTypeClusterLayout = (centerId?: string) => {
  applyGroupClusterLayout(
    (id) => nodeTypeById.value.get(id) ?? 'unknown',
    {
      placementOf: assuranceBandPlacement,
      anchorIds: new Set([centerId ?? rootId.value]),
    },
    keepFramed,
  )
}

const applyHopRadialLayout = () => {
  applyRadialLayout(hopById.value, RADIAL_RING_SPACING)
  keepFramed()
}

/** Re-run whichever layout is current — what every structural change needs. */
const relayout = (centerId?: string) => {
  // Reclaim the framing first: expanding or collapsing changes what there is to look at, so
  // the new arrangement is shown in full. `keepFramed` then defers to the user, so a zoom
  // *during* the move survives it.
  fitToView()
  if (layoutMode.value === 'cluster') applyTypeClusterLayout(centerId)
  else if (layoutMode.value === 'radial') applyHopRadialLayout()
  else animateForceLayout(keepFramed)
}

const switchLayout = (mode: LayoutMode) => {
  fitToView()
  if (mode === 'cluster') applyTypeClusterLayout(panel.value.selectedNodeId ?? undefined)
  else if (mode === 'radial') applyHopRadialLayout()
  else animateForceLayout(keepFramed)
}

const applyPreset = (preset: SpacingPreset) => {
  options.repulsion = preset.repulsion
  options.idealDist = preset.idealDist
  relayout()
}

const nodeVisual = (n: GraphNode): NodeVisual => ({
  color: assuranceNodeColor(nodeTypeById.value.get(n.id) ?? ''),
  shape: 'circle',
  iconLetter: null,
})
const edgeVisual = (): EdgeVisual => ({ stroke: null, strokeWidth: null, dashArray: undefined })
const isRoot = (id: string) => id === rootId.value

const applyGraph = (response: AssuranceNeighborsResponse, merge: boolean) => {
  if (!merge) {
    nodes.value = []
    edges.value = []
    hopById.value = new Map()
  }
  // Hops in a merged response are measured from the node being expanded, so they are rebased
  // onto that node's own distance; without this a third-hop node re-enters the graph as a
  // first-hop one and the rings stop meaning distance from where the exploration began.
  const rebase = merge ? hopById.value.get(response.root_id) ?? 0 : 0
  for (const node of response.nodes) {
    nodeTypeById.value.set(node.node_id, node.node_type)
    if (!hopById.value.has(node.node_id)) hopById.value.set(node.node_id, rebase + node.hop)
    addNode({
      id: node.node_id,
      label: node.name,
      type: nodeTypeLabel(node.node_id),
      addedBy: merge && !node.is_root ? response.root_id : undefined,
    })
  }
  for (const edge of response.edges) {
    addEdge({ source: edge.source_id, target: edge.target_id, connType: edge.conn_type })
  }
  markExpanded(response.root_id)
  if (merge) {
    // An expansion is the one moment the graph should move, and it has to be seen to move:
    // a rearrangement applied between two paints reads as the graph vanishing and coming
    // back already expanded. `relayout` honours whichever mode the user has chosen.
    relayout(response.root_id)
    return
  }
  // One tick, so the canvas has the nodes just assigned above: fitting within the same tick
  // measures the previous (often empty) array and silently leaves the view unfitted. This is
  // the path taken by "Explore graph" from the sidebar, which is where it showed.
  applyHopRadialLayout()
}

const fetchNeighbors = async (nodeId: string, merge: boolean) => {
  if (!nodeId || panel.value.lockedMessage) return
  loading.value = true
  try {
    const resp = await fetch(`/api/assurance/nodes/${encodeURIComponent(nodeId)}/neighbors`)
    const body: unknown = await resp.json().catch(() => null)
    const outcome = outcomeForResponse(resp.status, body)
    panel.value = panelStateForOutcome(outcome, panel.value)
    if (clearsGraph(outcome)) {
      nodes.value = []
      edges.value = []
      selectedEdge.value = null
      return
    }
    if (outcome.kind === 'graph') applyGraph(outcome.response, merge)
  } catch {
    panel.value = { ...panel.value, errorMessage: 'Neighbor request failed.', retryable: true }
  } finally {
    loading.value = false
  }
}

const loadRoot = () => {
  panel.value = { ...emptyPanelState(), selectedNodeId: rootId.value || null }
  void fetchNeighbors(rootId.value, false)
}

onMounted(loadRoot)
watch(rootId, loadRoot)

const onNodeClick = (n: GraphNode) => {
  panel.value = { ...panel.value, selectedNodeId: n.id }
  selectedEdge.value = null
}
const onNodeDblClick = (n: GraphNode) => {
  // Expansion is reversible here, as it is in the architecture explorer. Without the collapse
  // half, walking a neighbourhood is one-way: every double-click adds, nothing removes, and
  // the only way back to a readable graph is to reload and start over.
  if (n.expanded) {
    collapseNode(n.id)
    relayout(n.id)
    return
  }
  void fetchNeighbors(n.id, true)
}

// + badge: a node that has not been expanded yet. The store answers one hop at a time and
// never reports a degree, so unlike the architecture explorer there is no count to compare
// against — "not yet expanded" is the whole of what can honestly be offered here.
const showExpandBadge = (n: GraphNode) => !n.expanded
const onEdgeClick = (e: GraphEdge) => {
  selectedEdge.value = e
  panel.value = { ...panel.value, selectedNodeId: null }
}
const retry = () => {
  void fetchNeighbors(rootId.value, false)
}
</script>

<template>
  <div class="graph-layout">
    <div class="graph-canvas">
      <div class="canvas-header">
        <RouterLink
          v-if="rootId"
          :to="{ path: '/assurance', query: { node_id: rootId } }"
          class="back-link"
        >
          ← Back to browse
        </RouterLink>
        <span class="canvas-title">Assurance Graph</span>
        <span class="canvas-hint">Double-click a node to expand its neighbours, again to collapse them</span>
        <GraphLayoutToolbar
          v-if="!panel.lockedMessage"
          :viewpoint-active="false"
          :layout-mode="layoutMode"
          :layout-modes="ASSURANCE_LAYOUT_MODES"
          :ideal-dist="options.idealDist"
          @switch-layout="switchLayout"
          @apply-preset="applyPreset"
        />
      </div>
      <div
        v-if="!rootId"
        class="panel-banner"
      >
        Pick a starting node:
        <RouterLink to="/assurance">
          browse the assurance nodes
        </RouterLink>
        and use “Explore graph” on a node's detail panel.
      </div>
      <div
        v-else-if="panel.lockedMessage"
        class="panel-banner panel-banner--locked"
      >
        {{ panel.lockedMessage }}
      </div>
      <div
        v-else-if="panel.errorMessage"
        class="panel-banner panel-banner--error"
      >
        {{ panel.errorMessage }}
        <button
          v-if="panel.retryable"
          type="button"
          class="retry-btn"
          @click="retry"
        >
          Retry
        </button>
      </div>
      <GraphCanvas
        v-if="!panel.lockedMessage"
        ref="canvasRef"
        :nodes="nodes"
        :edges="edges"
        :selected-id="panel.selectedNodeId"
        :selected-edge="selectedEdge"
        :node-visual="nodeVisual"
        :edge-visual="edgeVisual"
        :is-anchor="isRoot"
        :show-expand-badge="showExpandBadge"
        :loading="loading"
        :notice="panel.truncationNotice"
        @node-click="onNodeClick"
        @node-dblclick="onNodeDblClick"
        @edge-click="onEdgeClick"
        @resized="onCanvasResized"
      />
    </div>

    <aside class="graph-sidebar">
      <h2 class="sidebar-title">
        Details
      </h2>
      <div
        v-if="selectedEdge"
        class="edge-summary"
      >
        <span class="mono">{{ selectedEdge.source }}</span>
        <span class="edge-conn-type">{{ selectedEdge.connType }}</span>
        <span class="mono">{{ selectedEdge.target }}</span>
      </div>
      <AssuranceNodeDetail
        v-else-if="panel.selectedNodeId"
        :node-id="panel.selectedNodeId"
      />
      <div
        v-else
        class="sidebar-empty"
      >
        Click a node or edge to view details
      </div>
    </aside>
  </div>
</template>

<style scoped>
.graph-layout { display: flex; height: calc(100vh - 96px); gap: 0; margin: -24px; }
/* min-width: 0 — a flex item defaults to min-width: auto, so the canvas column was sized by
   its header's intrinsic width rather than by the space left over. The header grows as the
   viewpoint controls fill in, which widened the canvas mid-load and pushed the fixed-width
   sidebar past the right edge of the viewport. */
.graph-canvas {
  flex: 1; min-width: 0; display: flex; flex-direction: column;
  background: #fafafa; position: relative;
}
.canvas-header {
  display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 12px 16px;
  border-bottom: 1px solid #e5e7eb; background: white;
}
.back-link { font-size: 13px; color: #6b7280; }
.back-link:hover { color: #374151; }
.canvas-title { font-size: 14px; font-weight: 600; color: #374151; }
.canvas-hint { font-size: 12px; color: #6b7280; margin-right: auto; }

.panel-banner { font-size: 13px; padding: 10px 16px; }
.panel-banner--locked { background: #fef9c3; color: #854d0e; border-bottom: 1px solid #facc15; }
.panel-banner--error { background: #fee2e2; color: #991b1b; border-bottom: 1px solid #fca5a5; }
.retry-btn {
  margin-left: 8px; padding: 2px 10px; border: 1px solid #d1d5db; border-radius: 4px;
  background: white; font-size: 12px; cursor: pointer; color: #374151;
}
.retry-btn:hover { background: #f3f4f6; }

.graph-sidebar {
  width: 320px; background: white; border-left: 1px solid #e5e7eb;
  overflow-y: auto; flex-shrink: 0;
}
.sidebar-title { font-size: 14px; font-weight: 600; color: #374151; margin: 16px; }
.sidebar-empty { font-size: 13px; color: #6b7280; margin: 0 16px; }
.edge-summary {
  display: flex; flex-direction: column; gap: 4px; margin: 0 16px;
  font-size: 12px; color: #374151;
}
.edge-conn-type { color: #6b7280; font-style: italic; }
.mono { font-family: monospace; }
</style>
