<script setup lang="ts">
import { entityDetailRoute } from '../router/artifactRoutes'
import { inject, nextTick, onMounted, watch, computed, ref } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { useQuery } from '../composables/useQuery'
import { useForceGraph, type GraphNode, type GraphEdge } from '../composables/useForceGraph'
import { useGraphFacets } from '../composables/useGraphFacets'
import GraphFilterPanel from '../components/GraphFilterPanel.vue'
import GraphCanvas from '../components/GraphCanvas.vue'
import { useViewpointExecution } from '../composables/useViewpointExecution'
import { useViewpointParameterPrompt } from '../composables/useViewpointParameterPrompt'
import type { ResolvedViewpointExecution } from '../composables/useViewpointParameterPrompt'
import GraphExploreSidebar from '../components/GraphExploreSidebar.vue'
import AggregationBanner from '../components/AggregationBanner.vue'
import ExecutionReferenceBar from '../components/ExecutionReferenceBar.vue'
import GraphLayoutToolbar from '../components/GraphLayoutToolbar.vue'
import DomainColorLegend from '../components/DomainColorLegend.vue'
import EdgeProvenanceLegend from '../components/EdgeProvenanceLegend.vue'
import HopDistanceLegend from '../components/HopDistanceLegend.vue'
import ViewpointSelect from '../components/ViewpointSelect.vue'
import ViewpointExecutionDiagnostics from '../components/ViewpointExecutionDiagnostics.vue'
import ViewpointExecutionError from '../components/ViewpointExecutionError.vue'
import ViewpointParameterPrompt from '../components/ViewpointParameterPrompt.vue'
import { computeExecutionDiagnostics, deriveLegend, deriveScaleGradients } from '../components/ViewpointExecutionDiagnostics.helpers'
import {
  nodeVisualFor, edgeVisualFor,
  buildConnectionStyleIndex, buildConnectionSummaryIndex, edgeStyleKey, projectionByItemId, explorationRedirectFor,
  distanceColor, effectiveExplorationFill, fetchRelationNotations, DOMAIN_COLORS,
} from './GraphExploreView.helpers'
import { useExplorationLayout } from '../composables/useExplorationLayout'
import { useFreeExploration } from '../composables/useFreeExploration'
import type { SpacingPreset } from '../composables/graphSpacingPresets'
import { useFreeExplorationLayout, FREE_LAYOUT_MODES } from '../composables/useFreeExplorationLayout'
import type { ParameterDraft } from '../lib/viewpointExecutionParameters'
import { VERIFIED_KEYS, executionQuery, parametersFromQuery } from '../lib/viewpointUrlState'
import { viewpointSummaryFromEnvelope } from '../lib/viewpointSummary'
import { useAggregatedExploration } from '../composables/useAggregatedExploration'
import { presentationFromMapping } from '../../domain/viewpointPresentationSerialization'
import type { PresentationNode } from '../../domain/viewpointPresentation'
import type { AdHocExecution } from '../lib/adHocExecution'
import type {
  EntityDetail, NotFoundError, ViewpointSummary, ViewpointDefinitionEnvelope,
} from '../../domain'
import type { MarkdownError } from '../../application/MarkdownService'
import type { RepoError } from '../../ports/ModelRepository'

const props = defineProps<{ adHoc?: AdHocExecution }>()

const svc = inject(modelServiceKey)!
const route = useRoute()
const router = useRouter()
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
} = useForceGraph(() => svgWidth.value, () => svgHeight.value)

// `facets.visible` is what the canvas draws: a filter hides from the picture, never from the model.
const facets = useGraphFacets<GraphNode, GraphEdge>({ svc, nodes, edges })

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

// ── Viewpoint-driven exploration ────────────────────────────────────────────

const viewpoints = ref<ViewpointSummary[]>([])
const viewpointDefinitions = ref<readonly ViewpointDefinitionEnvelope[]>([])
const selectedViewpointSlug = ref<string | null>(null)
const viewpointExecution = useViewpointExecution(svc)

const loadViewpointCatalog = async () => {
  // Viewpoint discovery comes from the dedicated /api/viewpoints source, not authoring
  // guidance — the picker summaries are projected from the same definition envelopes.
  const definitions = await Effect.runPromise(svc.listViewpointDefinitions()).catch(() => [])
  viewpointDefinitions.value = definitions
  viewpoints.value = definitions.map(viewpointSummaryFromEnvelope)
}

const selectedPresentation = computed<PresentationNode | null>(() => {
  if (props.adHoc) return props.adHoc.presentation
  const envelope = viewpointDefinitions.value.find((d) => d.slug === selectedViewpointSlug.value)
  return envelope ? presentationFromMapping(envelope.presentation) : null
})
const currentRepresentation = computed(() => selectedPresentation.value?.representation ?? 'exploration')
const entityStyleById = computed(() => projectionByItemId(viewpointExecution.projection.value))
const connectionStyleIndex = computed(() =>
  buildConnectionStyleIndex(viewpointExecution.result.value?.connections ?? [], viewpointExecution.projection.value),
)
const connectionSummaryIndex = computed(() =>
  buildConnectionSummaryIndex(viewpointExecution.result.value?.connections ?? []),
)
const selectedEdgeSummary = computed(() => {
  const edge = selectedEdge.value
  if (!edge) return null
  return connectionSummaryIndex.value.get(edgeStyleKey(edge.source, edge.target, edge.connType)) ?? null
})
const diagnostics = computed(() => computeExecutionDiagnostics(
  viewpointExecution.result.value, selectedPresentation.value, currentRepresentation.value,
))
const selectedEnvelope = computed(() =>
  viewpointDefinitions.value.find((d) => d.slug === selectedViewpointSlug.value) ?? null,
)
const legend = computed(() => deriveLegend(selectedPresentation.value, viewpointExecution.projection.value?.rule_outcomes ?? []))
const scaleGradients = computed(() => deriveScaleGradients(selectedPresentation.value, viewpointExecution.projection.value?.scale_legends ?? []))

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

const runViewpointExecution = async (resolved: ResolvedViewpointExecution) => {
  nodes.value = []
  edges.value = []
  selectedId.value = null
  selectedEdge.value = null
  // URL = state: the address always names the ON-SCREEN execution (slug + parameters).
  // Verification pins survive only a same-viewpoint re-run/reload — switching viewpoints
  // must never carry a previous reference's pins forward.
  const pins = route.query.viewpoint === resolved.slug
    ? Object.fromEntries(VERIFIED_KEYS.flatMap((key) => (typeof route.query[key] === 'string' ? [[key, route.query[key]]] : [])))
    : {}
  void router.replace({ query: { ...executionQuery(resolved.slug, resolved.parameters), ...pins } })
  await viewpointExecution.execute(resolved)
  resetExpansion()
  populateFromResult()
}
const viewpointPrompt = useViewpointParameterPrompt(runViewpointExecution, viewpointDefinitions)
const loadViewpointPopulation = (slug: string, preset?: ParameterDraft) => viewpointPrompt.run(slug, preset)

// Ad-hoc exploration: execute an inline query + presentation directly (no slug/picker/URL),
// then populate the graph from the same result the saved path uses.
const runAdHocExploration = async () => {
  if (!props.adHoc) return
  nodes.value = []
  edges.value = []
  selectedId.value = null
  selectedEdge.value = null
  await viewpointExecution.execute(props.adHoc.request)
  resetExpansion()
  populateFromResult()
}

const onSelectViewpoint = (viewpoint: ViewpointSummary | null) => {
  selectedViewpointSlug.value = viewpoint?.slug ?? null
  if (!viewpoint) {
    viewpointExecution.clear()
    void router.replace({ query: rootId.value ? { id: rootId.value } : {} })
    loadRoot()
    return
  }
  const envelope = viewpointDefinitions.value.find((d) => d.slug === viewpoint.slug)
  const redirect = explorationRedirectFor(envelope)
  if (redirect) {
    void router.push(redirect)
    return
  }
  void loadViewpointPopulation(viewpoint.slug)
}

const rerunViewpoint = () => {
  if (selectedViewpointSlug.value) void loadViewpointPopulation(selectedViewpointSlug.value)
}

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

const applyPreset = (p: SpacingPreset) => {
  options.repulsion = p.repulsion
  options.idealDist = p.idealDist
  relayoutForMode()
}

const { applyDomainClusterLayout, relayout: relayoutForMode, switchLayout } = useFreeExplorationLayout({
  nodes, rootId, layoutMode,
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
  void loadViewpointCatalog().then(() => {
    const viewpointSlug = route.query.viewpoint as string | undefined
    const preselected = viewpointSlug ? viewpoints.value.find((v) => v.slug === viewpointSlug) : undefined
    if (!preselected) return
    const envelope = viewpointDefinitions.value.find((d) => d.slug === preselected.slug)
    const redirect = explorationRedirectFor(envelope)
    if (redirect) {
      void router.push(redirect)
      return
    }
    // Reload/shared link: URL-carried parameters execute directly (no re-prompt).
    selectedViewpointSlug.value = preselected.slug
    void loadViewpointPopulation(preselected.slug, parametersFromQuery(route.query))
  })
  loadRoot()
})
watch(rootId, () => { if (selectedViewpointSlug.value === null) loadRoot() })

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
        <div
          v-if="!adHoc"
          class="spacing-controls"
        >
          <span class="spacing-label">Viewpoint:</span>
          <ViewpointSelect
            :model-value="selectedViewpointSlug"
            :viewpoints="viewpoints"
            @select="onSelectViewpoint"
          />
        </div>
        <GraphFilterPanel
          v-bind="facets.panelProps.value"
          @toggle="facets.toggle"
          @reset="facets.reset"
        />
        <GraphLayoutToolbar
          :viewpoint-active="selectedViewpointSlug !== null"
          :layout-mode="layoutMode"
          :layout-modes="FREE_LAYOUT_MODES"
          :layout-override="layoutOverride"
          :ideal-dist="options.idealDist"
          :radial-available="anchorIds.length > 0"
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
      />
    </div>

    <GraphExploreSidebar
      :selected-id="selectedId"
      :selected-edge="selectedEdge"
      :selected-edge-summary="selectedEdgeSummary"
      :detail="sd ?? null"
      :loading="selectedDetail.loading.value"
      :error-message="selectedDetail.errorMessage.value"
    />
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

.spacing-controls { display: flex; align-items: center; gap: 4px; }
.spacing-label { font-size: 11px; color: #6b7280; margin-right: 4px; }
.spacing-btn {
  padding: 3px 8px; border-radius: 4px; border: 1px solid #d1d5db;
  background: white; font-size: 11px; cursor: pointer; color: #374151;
}
/* Hover is excluded on the selected button and given its own darker shade there. A bare
   `:hover` rule outranks the single-class active rule, so hovering the selected button
   restored the pale hover background while the active rule's white text stayed — the
   label disappeared for as long as the pointer rested on it. */
.spacing-btn:hover:not(.spacing-btn--active) { background: #f3f4f6; }
.spacing-btn--active { background: #2563eb; color: white; border-color: #2563eb; }
.spacing-btn--active:hover { background: #1d4ed8; }


.mono { font-family: monospace; }
</style>
