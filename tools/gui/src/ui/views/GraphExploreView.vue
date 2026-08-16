<script setup lang="ts">
import { entityDetailRoute } from '../router/artifactRoutes'
import { inject, nextTick, onMounted, watch, computed, ref, toRef } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { modelServiceKey } from '../keys'
import { useQuery } from '../composables/useQuery'
import { useForceGraph, type GraphNode, type GraphEdge } from '../composables/useForceGraph'
import { useGraphFacets } from '../composables/useGraphFacets'
import GraphCanvas from '../components/GraphCanvas.vue'
import FullscreenDock from '../components/FullscreenDock.vue'
import GraphExploreSidebar from '../components/GraphExploreSidebar.vue'
import GraphExploreToolbar from '../components/GraphExploreToolbar.vue'
import AggregationBanner from '../components/AggregationBanner.vue'
import ExecutionReferenceBar from '../components/ExecutionReferenceBar.vue'
import DomainColorLegend from '../components/DomainColorLegend.vue'
import EdgeProvenanceLegend from '../components/EdgeProvenanceLegend.vue'
import HopDistanceLegend from '../components/HopDistanceLegend.vue'
import ViewpointExecutionDiagnostics from '../components/ViewpointExecutionDiagnostics.vue'
import ViewpointExecutionError from '../components/ViewpointExecutionError.vue'
import ViewpointParameterPrompt from '../components/ViewpointParameterPrompt.vue'
import {
  nodeVisualFor, edgeVisualFor, edgeStyleKey,
  distanceColor, effectiveExplorationFill, fetchRelationNotations, DOMAIN_COLORS,
} from './GraphExploreView.helpers'
import { useExplorationLayout } from '../composables/useExplorationLayout'
import { useFreeExploration } from '../composables/useFreeExploration'
import { useGraphViewpointExploration } from '../composables/useGraphViewpointExploration'
import { useGraphSnapshot } from '../composables/useGraphSnapshot'
import { SPACING_PRESETS, type SpacingPreset } from '../composables/graphSpacingPresets'
import { useFreeExplorationLayout, FREE_LAYOUT_MODES } from '../composables/useFreeExplorationLayout'
import { useAggregatedExploration } from '../composables/useAggregatedExploration'
import type { AdHocExecution } from '../lib/adHocExecution'
import type { EntityDetail, NotFoundError } from '../../domain'
import type { MarkdownError } from '../../application/MarkdownService'
import type { RepoError } from '../../ports/ModelRepository'

const props = defineProps<{ adHoc?: AdHocExecution }>()

const svc = inject(modelServiceKey)!
const route = useRoute()
// Absent on the unanchored exploration route, which shows a viewpoint's whole population.
const rootId = computed(() => (route.params.artifactId as string | undefined) ?? '')

const canvasRef = ref<InstanceType<typeof GraphCanvas> | null>(null)
const svgWidth = ref(800)
const svgHeight = ref(600)
const onCanvasResized = (width: number, height: number) => {
  svgWidth.value = width
  svgHeight.value = height
}
const selectedId = ref<string | null>(null)
const selectedDetail = useQuery<EntityDetail, RepoError | NotFoundError | MarkdownError>()

const {
  nodes, edges, options, layoutMode,
  addNode, addEdge, markExpanded, collapseNode, spreadAroundParent, settleForceLayout,
  animateForceLayout, applyGroupClusterLayout, applyRadialLayout,
} = useForceGraph(() => svgWidth.value, () => svgHeight.value, 'radial')

// `facets.visible` is what the canvas draws: a filter hides from the picture, never from the model.
const keepWhateverIsFiltered = computed(() => (rootId.value ? [rootId.value] : []))

const facets = useGraphFacets<GraphNode, GraphEdge>({
  svc, nodes, edges, alwaysKeep: keepWhateverIsFiltered,
})

/** Bring the force layout to rest and frame it — the pair every structural change needs. */
const settleAndFit = () => { settleForceLayout(); fitToView() }

const onDragTick = () => {
  if (layoutMode.value !== 'force') return
  // Nothing runs while the pointer is down: the dragged node already follows it, and letting
  // the simulation run means every *other* node drifts under the user's hand. One synchronous
  // settle on release, so the graph is at rest — and hit-testable — the moment it is let go.
  if (canvasRef.value?.dragging) return
  settleAndFit()
}
const fitToView = () => {
  // Deferred by one tick on purpose. Callers fit immediately after replacing `nodes`, but
  // the canvas reads them as a prop, so within the same tick it still sees the previous
  // array — and for the common case of "populate, then fit" that array is empty. Fitting an
  // empty set yields the identity box, which looks like the fit simply never happened: the
  // graph sits wherever the layout put it, at whatever scale the container had on mount.
  void nextTick(() => { canvasRef.value?.fitToView() })
}

/**
 * Keep the graph framed *while* it moves, unless the user has framed it themselves.
 *
 * The per-frame callback for animated layouts. It cannot be a plain `fitToView`: that runs on
 * every frame of a three-second animation and overwrites the viewBox each time, so a wheel
 * zoom during the motion was undone on the very next frame and the control read as dead. The
 * user's framing wins from the moment they touch it — which is the contract
 * `refitUnlessUserFramed` already states for container resizes.
 */
const keepFramed = () => {
  void nextTick(() => { canvasRef.value?.refitUnlessUserFramed() })
}

// Selected edge (connection) for sidebar
const selectedEdge = ref<GraphEdge | null>(null)

/**
 * Clicking away from everything deselects, which is what flies the sidebar back out in fullscreen.
 *
 * The same affordance a diagram offers, and the reason the dock reveals on selection at all: over a
 * graph filling the screen a permanent panel covers the thing being read, so there has to be a way
 * to put it away that is not "select something else".
 */
const clearGraphSelection = () => {
  selectedId.value = null
  selectedEdge.value = null
}

/** Nothing drawn and nothing selected — what every incoming population starts from. */
const clearGraph = () => {
  nodes.value = []
  edges.value = []
  clearGraphSelection()
}

const { snapshotError, takeSnapshot } = useGraphSnapshot(
  () => (canvasRef.value ? { svgEl: canvasRef.value.svgEl, frame: canvasRef.value.frame } : null),
  () => sd.value?.name ?? rootId.value,
)

// ── Viewpoint-driven exploration ────────────────────────────────────────────
// The catalog, the execution and everything read off a result. The graph itself stays here:
// what a population does to the picture is this view's business, so it is passed in.

const {
  viewpoints, selectedViewpointSlug, viewpointExecution, viewpointPrompt,
  selectedPresentation, entityStyleById, connectionStyleIndex, connectionSummaryIndex,
  diagnostics, selectedEnvelope, legend, scaleGradients,
  loadViewpointCatalog, runAdHocExploration, restoreFromAddress, onSelectViewpoint, rerunViewpoint,
} = useGraphViewpointExploration(svc, { adHoc: toRef(props, 'adHoc'), rootId }, {
  clearGraph,
  populate: () => { resetExpansion(); populateFromResult() },
  loadRoot: () => loadRoot(),
})

const selectedEdgeSummary = computed(() => {
  const edge = selectedEdge.value
  if (!edge) return null
  return connectionSummaryIndex.value.get(edgeStyleKey(edge.source, edge.target, edge.connType)) ?? null
})

// ── Anchored executions: hop distances, distance fill, anchor marking ───────

const {
  anchorIds, isAnchor, hopDepthById, maxHopDepth, hasUnrankedNodes,
  layoutOverride, applyExplorationLayout, setExplorationLayout,
} = useExplorationLayout(viewpointExecution.result, selectedPresentation, {
  applyRadialLayout, settleForceLayout, applyGroupClusterLayout, fitToView,
})

// ── Scale-adaptive aggregation (over-budget populations open as super-nodes) ──
const {
  activeAggregation, aggregationHint, missingMemberCount,
  populateFromResult, toggleAggregate, resetExpansion, isAggregateNodeId,
} = useAggregatedExploration(viewpointExecution.result, {
  clear: () => { nodes.value = []; edges.value = [] },
  addNode,
  addEdge,
  finalize: () => {
    for (const n of nodes.value) void resolveNodeDomain(n)
    applyExplorationLayout()
  },
})

/** The fill for nodes the projection leaves uncolored — by domain unless the presentation
 * asks for hop distance. A projection-provided `node_color` still wins in `nodeVisualFor`. */
const explorationFill = computed(() =>
  effectiveExplorationFill(selectedPresentation.value?.displayOptions['color_by'], maxHopDepth.value),
)
const nodeFallbackFill = (n: GraphNode) => {
  const depth = hopDepthById.value.get(n.id)
  return explorationFill.value === 'hop-distance' && depth !== undefined
    ? distanceColor(depth, maxHopDepth.value)
    : DOMAIN_COLORS[n.domain ?? ''] ?? '#6b7280'
}
const nodeVisual = (n: GraphNode) =>
  nodeVisualFor(entityStyleById.value.get(n.id)?.style, nodeFallbackFill(n), n.artifactType)
//: Relationship notation from the ontology — line style and the marker at each end. Fetched
//: once for the surface rather than per edge, and empty until it arrives, which renders the
//: previous plain arrow for a frame rather than nothing.
const relationNotations = ref<ReadonlyMap<string, import('./GraphExploreView.helpers').RelationNotation>>(new Map())
void fetchRelationNotations().then((n) => { relationNotations.value = n })

const edgeVisual = (e: GraphEdge) => {
  const key = edgeStyleKey(e.source, e.target, e.connType)
  return edgeVisualFor(
    connectionStyleIndex.value.get(key),
    connectionSummaryIndex.value.get(key)?.certainty ?? null,
    relationNotations.value.get(e.connType),
  )
}

/** The spacing rung in force, so every layout can read its own units from one choice. */
const spacing = ref<SpacingPreset>(SPACING_PRESETS[1])

const applyPreset = (p: SpacingPreset) => {
  spacing.value = p
  options.repulsion = p.repulsion
  options.idealDist = p.idealDist
  relayoutForMode()
}

const { applyDomainClusterLayout, relayout: relayoutForMode, switchLayout } = useFreeExplorationLayout({
  nodes, rootId, layoutMode,
  ringSpacing: () => spacing.value.ringSpacing,
  labelArc: () => spacing.value.labelArc,
  cellGap: () => spacing.value.cellGap,
  applyGroupClusterLayout, applyRadialLayout, animateForceLayout, fitToView, keepFramed,
})

// ── Data loading ─────────────────────────────────────────────────────────────

const { resolveNodeDomain, expandNode, loadRoot } = useFreeExploration({
  svc, nodes, edges, rootId,
  addNode, addEdge, markExpanded, spreadAroundParent,
  relayout: relayoutForMode, isAggregateNodeId,
  selectNode: (id) => { selectedId.value = id; selectNode(id) },
})

/**
 * Re-lay the clusters whenever the population changes, whatever changed it.
 *
 * Expansions overlap: double-clicking a second node while the first is still fetching adds
 * nodes *after* that first expansion computed its layout, and a layout is a snapshot — the
 * late arrivals were never in it, so they stayed wherever the initial scatter dropped them,
 * on top of whatever was already there. Making the layout self-correcting is what closes
 * that off, rather than trying to serialise every path that can add a node.
 *
 * Cannot recurse: laying out moves nodes, it never adds or removes them.
 */
watch(() => nodes.value.length, () => {
  if (layoutMode.value !== 'cluster' || selectedViewpointSlug.value !== null) return
  void nextTick(() => applyDomainClusterLayout())
})

onMounted(() => {
  if (props.adHoc) {
    void loadViewpointCatalog().then(() => runAdHocExploration())
    return
  }
  void loadViewpointCatalog().then(() => restoreFromAddress())
  loadRoot()
})
watch(rootId, () => { if (selectedViewpointSlug.value === null) loadRoot() })

/**
 * Re-arrange when the filter changes what is on screen.
 *
 * Every layout places nodes against the population it was given, so a filtered graph left in the
 * old arrangement is the *unfiltered* one with pieces missing — a radial ring with gaps in it, a
 * cluster grid with empty cells, and a fit that frames the space the hidden nodes used to occupy.
 * Watched on the count rather than on the selection, so that toggling a value that hides nothing
 * does not rearrange the graph under the reader for no visible reason.
 */
watch(() => facets.visible.value.nodes.length, (now, before) => {
  if (now !== before && now > 0) relayoutForMode()
})

// ── Selection ────────────────────────────────────────────────────────────────

const selectNode = (id: string) => {
  selectedId.value = id
  selectedEdge.value = null
  selectedDetail.run(svc.getEntity(id))
}

const onEdgeClick = (e: typeof edges.value[number]) => {
  selectedEdge.value = e
  selectedId.value = null
}

const onNodeClick = (n: GraphNode) => {
  if (isAggregateNodeId(n.id)) {
    toggleAggregate(n.id)
    return
  }
  selectNode(n.id)
}

const onNodeDblClick = (n: GraphNode) => {
  // A viewpoint's result is a fixed population — no incremental expand/collapse.
  if (selectedViewpointSlug.value !== null) return
  if (n.expanded) {
    collapseNode(n.id)
    relayoutForMode(n.id)
  } else {
    expandNode(n.id)
  }
}


const sd = computed(() => selectedDetail.data.value)

/**
 * Which nodes carry the anchor ring.
 *
 * A viewpoint execution names its own anchors. Free exploration has exactly one — the entity
 * the route opened on — and it used to be marked no differently from anything else, so a few
 * expansions in there was nothing on screen saying where the walk had started. The ring is the
 * same one anchored viewpoint presentations use, deliberately: one meaning, one marking.
 */
const isAnchorNode = (id: string) =>
  isAnchor(id) || (selectedViewpointSlug.value === null && !props.adHoc && id === rootId.value)

const shownEdgeCount = (nodeId: string) =>
  edges.value.filter((e) => e.source === nodeId || e.target === nodeId).length

// + badge: unexpanded AND connections not yet shown (never in viewpoint mode: a
// viewpoint's population is fixed, no incremental expand).
const showExpandBadge = (n: GraphNode) =>
  selectedViewpointSlug.value === null && !n.expanded
  && (n.totalConns === undefined || n.totalConns > shownEdgeCount(n.id))
</script>

<template>
  <div class="graph-layout">
    <div class="graph-canvas">
      <div class="canvas-header">
        <RouterLink
          v-if="rootId"
          :to="entityDetailRoute(rootId)"
          class="back-link"
        >
          ← Back to entity
        </RouterLink>
        <span class="canvas-title">Graph Explorer</span>
        <RouterLink
          v-if="!adHoc && selectedViewpointSlug"
          :to="{ path: '/viewpoints/query', query: { slug: selectedViewpointSlug } }"
          class="view-as-link"
          title="Re-present this saved viewpoint with a different presentation, without changing it"
        >
          View as… (unsaved)
        </RouterLink>
        <!-- In the header row normally; over the canvas once it owns the screen. Docked by the
             same component the sidebar uses, so the two move by one mechanism. -->
        <GraphExploreToolbar
          :fullscreen-host="canvasRef?.frameEl ?? null"
          :is-fullscreen="canvasRef?.isFullscreen ?? false"
          :show-viewpoint-picker="!adHoc"
          :selected-viewpoint-slug="selectedViewpointSlug"
          :viewpoints="viewpoints"
          :filter="facets.panelProps.value"
          :layout="{
            viewpointActive: selectedViewpointSlug !== null,
            layoutMode,
            layoutModes: FREE_LAYOUT_MODES,
            layoutOverride,
            activeSpacing: spacing.label,
            radialAvailable: anchorIds.length > 0,
          }"
          @select-viewpoint="onSelectViewpoint"
          @toggle-facet="facets.toggle"
          @reset-facets="facets.reset"
          @snapshot="takeSnapshot"
          @switch-layout="switchLayout"
          @set-exploration-layout="setExplorationLayout"
          @apply-preset="applyPreset"
        />
      </div>
      <ViewpointExecutionDiagnostics
        v-if="selectedViewpointSlug !== null && !viewpointPrompt.visible.value
          && !viewpointExecution.errorMessage.value"
        :diagnostics="diagnostics"
        :legend="legend"
        :scale-gradients="scaleGradients"
        :query-summary="viewpointExecution.result.value?.query_summary ?? ''"
        @rerun="rerunViewpoint"
      />
      <AggregationBanner
        v-if="activeAggregation"
        :aggregation="activeAggregation"
        :hint="aggregationHint"
        :total-entity-count="viewpointExecution.result.value?.total_entity_count ?? 0"
        :missing-member-count="missingMemberCount"
      />
      <ExecutionReferenceBar
        v-if="selectedViewpointSlug !== null"
        :envelope="selectedEnvelope"
        :result="viewpointExecution.result.value"
      />
      <HopDistanceLegend
        v-if="explorationFill === 'hop-distance'"
        :depths="[...hopDepthById.values()]"
        :has-unranked="hasUnrankedNodes"
      />
      <EdgeProvenanceLegend :connections="viewpointExecution.result.value?.connections ?? []" />
      <DomainColorLegend :domains="nodes.map((n) => n.domain)" />
      <ViewpointParameterPrompt
        v-if="viewpointPrompt.visible.value"
        :parameters="viewpointPrompt.parameters.value"
        @submit="viewpointPrompt.submit"
        @cancel="viewpointPrompt.cancel"
      />
      <ViewpointExecutionError
        v-if="selectedViewpointSlug !== null && viewpointExecution.errorMessage.value"
        :typed-error="viewpointExecution.typedError.value"
        :fallback-message="viewpointExecution.errorMessage.value"
        @retry="rerunViewpoint"
      />
      <p
        v-if="snapshotError"
        class="snapshot-error"
        role="status"
      >
        The snapshot could not be taken: {{ snapshotError }}
      </p>
      <GraphCanvas
        ref="canvasRef"
        :nodes="facets.visible.value.nodes"
        :edges="facets.visible.value.edges"
        :selected-id="selectedId"
        :selected-edge="selectedEdge"
        :node-visual="nodeVisual"
        :edge-visual="edgeVisual"
        :is-anchor="isAnchorNode"
        :show-expand-badge="showExpandBadge"
        :cluster-edges="layoutMode === 'cluster'"
        @node-click="onNodeClick"
        @node-dblclick="onNodeDblClick"
        @edge-click="onEdgeClick"
        @drag-tick="onDragTick"
        @resized="onCanvasResized"
        @background-click="clearGraphSelection"
      />
    </div>

    <!-- Beside the canvas normally; teleported inside it once it owns the screen, because the
         browser paints nothing outside a fullscreen element and a docked panel would simply
         vanish. Revealed on selection there, since a permanent panel over a full-screen graph
         covers the thing being read most of the time. Same component, same rule, as a diagram. -->
    <FullscreenDock
      :fullscreen-host="canvasRef?.frameEl ?? null"
      :is-fullscreen="canvasRef?.isFullscreen ?? false"
      :revealed="selectedId !== null || selectedEdge !== null"
    >
      <GraphExploreSidebar
        :selected-id="selectedId"
        :selected-edge="selectedEdge"
        :selected-edge-summary="selectedEdgeSummary"
        :detail="sd ?? null"
        :loading="selectedDetail.loading.value"
        :error-message="selectedDetail.errorMessage.value"
      />
    </FullscreenDock>
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
.canvas-title { font-size: 14px; font-weight: 600; color: #374151; margin-right: auto; }
.view-as-link { font-size: 12px; color: #4338ca; text-decoration: none; border: 1px solid #c7d2fe; border-radius: 6px; padding: 3px 9px; margin-right: 10px; }
.view-as-link:hover { background: #eef2ff; }

.snapshot-error {
  margin: 0; padding: 8px 16px; font-size: 13px; color: #b91c1c; background: #fef2f2;
}

.mono { font-family: monospace; }
</style>
