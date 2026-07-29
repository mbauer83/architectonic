<script setup lang="ts">
/**
 * One assurance projection, rendered: the SVG (or its matrix / plain-list fallback), pan/zoom,
 * and click-to-select. What a selection *shows* is not its concern — it reports the selection
 * and the hosting view decides where the detail goes, which is what lets the same panel sit in
 * a resizable split without knowing anything about the layout around it.
 */
import DOMPurify from 'dompurify'
import { computed, onMounted, ref, watch } from 'vue'
import WithheldNotice from './WithheldNotice.vue'
import { useFittedPanZoom } from '../composables/useFittedPanZoom'
import { useAssuranceSvgInteractions } from '../composables/useAssuranceSvgInteractions'
import {
  buildUcaMatrixRows,
  type AssuranceDiagramEdge,
  type AssuranceDiagramNode,
  type NodeRepresentingEdge,
} from './AssuranceDiagramPanel.helpers'
import { renderedDiagramUrl } from '../lib/assuranceDiagrams'
import { UCA_GUIDEWORDS } from '../lib/ucaGuidewords'

const props = defineProps<{
  /** A projection is one analysis' drawing of one type; neither half names it alone. */
  analysisId: string
  diagramType: string
  /** Currently selected node/edge, so the panel can mark it — owned by the host. */
  selectedNodeId?: string | null
  selectedEdgeId?: string | null
}>()

const emit = defineEmits<{
  'select-node': [nodeId: string]
  'select-edge': [edge: AssuranceDiagramEdge]
  /** The projection just (re)loaded: a previous selection no longer points at anything, and the
   * host needs the node/edge sets to describe whatever is selected next. */
  loaded: [projection: { nodes: AssuranceDiagramNode[]; edges: AssuranceDiagramEdge[] }]
}>()

const loading = ref(false)
const puml = ref<string | null>(null)
const svg = ref<string | null>(null)
const nodes = ref<AssuranceDiagramNode[]>([])
const edges = ref<AssuranceDiagramEdge[]>([])
const nodeRepresentingEdges = ref<NodeRepresentingEdge[]>([])
/** `{ plantuml alias: node id }`, published by whatever rendered the PUML. Never derived here. */
const nodeAliases = ref<Record<string, string>>({})
const error = ref<string | null>(null)
const visibilityLimited = ref(false)
const showPuml = ref(false)
const svgContainer = ref<HTMLElement | null>(null)
const containerRef = ref<HTMLElement | null>(null)
const panZoom = useFittedPanZoom(containerRef, svgContainer)

const matrixRows = computed(() => buildUcaMatrixRows(nodes.value, edges.value))
// Only for this panel's own no-SVG fallback list, which names an edge's endpoints inline.
const nodeNames = computed(() => new Map(nodes.value.map((node) => [node.node_id, node.name])))
const sanitizedSvg = computed(() => svg.value
  ? DOMPurify.sanitize(svg.value, {
      USE_PROFILES: { svg: true, svgFilters: true },
      ADD_ATTR: ['data-entity', 'data-entity-1', 'data-entity-2', 'data-qualified-name'],
    })
  : null)

const selectNode = (nodeId: string) => emit('select-node', nodeId)
const selectEdge = (edge: AssuranceDiagramEdge) => emit('select-edge', edge)

const { attachInteractivity, markSelection } = useAssuranceSvgInteractions({
  svgContainer, nodes, edges, nodeRepresentingEdges, nodeAliases,
  onSelectNode: selectNode, onSelectEdge: selectEdge,
})

const markCurrentSelection = () =>
  markSelection({ nodeId: props.selectedNodeId, edgeId: props.selectedEdgeId })

const edgeKey = (edge: AssuranceDiagramEdge): string =>
  edge.edge_id ?? `${edge.source_id}:${edge.target_id}`

async function load() {
  loading.value = true
  puml.value = null
  svg.value = null
  nodes.value = []
  edges.value = []
  nodeRepresentingEdges.value = []
  nodeAliases.value = {}
  error.value = null
  visibilityLimited.value = false
  try {
    const response = await fetch(renderedDiagramUrl(props.analysisId, props.diagramType))
    if (response.status === 423) { error.value = 'Store is locked.'; return }
    if (response.status === 404) { error.value = 'Diagram not found.'; return }
    if (!response.ok) { error.value = `HTTP ${response.status}`; return }
    const body = await response.json() as {
      puml: string | null
      svg: string | null
      nodes: AssuranceDiagramNode[]
      edges: AssuranceDiagramEdge[]
      node_representing_edges?: NodeRepresentingEdge[]
      node_aliases?: Record<string, string>
      visibility_limited: boolean
    }
    puml.value = body.puml
    svg.value = body.svg
    nodes.value = body.nodes
    edges.value = body.edges
    nodeRepresentingEdges.value = body.node_representing_edges ?? []
    nodeAliases.value = body.node_aliases ?? {}
    visibilityLimited.value = body.visibility_limited
  } catch (cause) {
    error.value = String(cause)
  } finally {
    loading.value = false
    emit('loaded', { nodes: nodes.value, edges: edges.value })
  }
}

watch(() => [props.analysisId, props.diagramType], load)
watch(sanitizedSvg, async (svg) => {
  await attachInteractivity()
  // A freshly rendered SVG carries no marks yet, so re-apply whatever is selected.
  markCurrentSelection()
  if (svg) void panZoom.fitDiagramToViewport()
}, { flush: 'post' })
watch(() => [props.selectedNodeId, props.selectedEdgeId], markCurrentSelection, { flush: 'post' })
onMounted(load)
</script>

<template>
  <div class="assurance-diagram-panel">
    <div
      v-if="loading"
      class="panel-state"
    >
      Loading…
    </div>
    <div
      v-else-if="error"
      class="panel-error"
    >
      {{ error }}
    </div>
    <template v-else>
      <WithheldNotice
        v-if="visibilityLimited"
        kind="diagram nodes"
      />

      <div class="diagram-content">
        <div
          v-if="sanitizedSvg"
          ref="containerRef"
          class="img-container"
          @mousedown="panZoom.onMouseDown"
          @dblclick="panZoom.resetView"
        >
          <div :style="panZoom.canvasStyle.value">
            <!-- eslint-disable-next-line vue/no-v-html -->
            <div
              ref="svgContainer"
              class="svg-wrap"
              v-html="sanitizedSvg"
            />
          </div>
          <button
            v-if="panZoom.isTransformed.value"
            class="reset-btn"
            title="Reset view"
            @click.stop="panZoom.resetView"
          >
            ⊙ Reset
          </button>
          <div class="zoom-hint">
            Scroll to zoom · Drag to pan · Click node/edge to inspect · Double-click to reset
          </div>
        </div>
        <div
          v-else-if="diagramType === 'uca-matrix'"
          class="uca-matrix-wrap"
        >
          <table class="uca-matrix">
            <thead>
              <tr>
                <th>Control action</th>
                <th
                  v-for="guideword in UCA_GUIDEWORDS"
                  :key="guideword.slug"
                >
                  {{ guideword.label }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in matrixRows"
                :key="row.controlAction.node_id"
              >
                <th>
                  <button
                    class="node-link"
                    @click="selectNode(row.controlAction.node_id)"
                  >
                    {{ row.controlAction.name }}
                  </button>
                </th>
                <td
                  v-for="guideword in UCA_GUIDEWORDS"
                  :key="guideword.slug"
                >
                  <button
                    v-for="node in row.cells[guideword.slug] ?? []"
                    :key="node.node_id"
                    class="uca-chip"
                    @click="selectNode(node.node_id)"
                  >
                    {{ node.name }}
                  </button>
                  <span
                    v-if="!(row.cells[guideword.slug]?.length)"
                    class="empty-cell"
                  >—</span>
                </td>
              </tr>
              <tr v-if="matrixRows.length === 0">
                <td
                  :colspan="UCA_GUIDEWORDS.length + 1"
                  class="empty-matrix"
                >
                  No control actions found.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div
          v-else
          class="diagram-fallback"
        >
          <p class="fallback-note">
            Diagram rendering is unavailable. Select a store node or edge below.
          </p>
          <div class="fallback-columns">
            <section>
              <h3>Nodes</h3>
              <button
                v-for="node in nodes"
                :key="node.node_id"
                class="fallback-item"
                :class="{ 'fallback-item--selected': selectedNodeId === node.node_id }"
                @click="selectNode(node.node_id)"
              >
                <strong>{{ node.name }}</strong>
                <span>{{ node.node_type }}</span>
              </button>
            </section>
            <section>
              <h3>Edges</h3>
              <button
                v-for="edge in edges"
                :key="edgeKey(edge)"
                class="fallback-item"
                :class="{ 'fallback-item--selected': selectedEdgeId === edgeKey(edge) }"
                @click="selectEdge(edge)"
              >
                <strong>{{ edge.conn_type }}</strong>
                <span>{{ nodeNames.get(edge.source_id) }} → {{ nodeNames.get(edge.target_id) }}</span>
              </button>
            </section>
          </div>
        </div>

        <div
          v-if="puml"
          class="puml-toggle"
        >
          <button
            class="puml-toggle-btn"
            @click="showPuml = !showPuml"
          >
            {{ showPuml ? 'Hide' : 'Show' }} PUML source
          </button>
          <pre
            v-if="showPuml"
            class="puml-source"
          >{{ puml }}</pre>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.assurance-diagram-panel { display: flex; flex-direction: column; gap: 12px; }
.panel-state { color: #64748b; font-size: 13px; }
.panel-error { color: #dc2626; font-size: 13px; }
.diagram-content { min-width: 0; }
.img-container {
  position: relative; overflow: hidden; background: #f8fafc;
  border: 1px solid #e2e8f0; border-radius: 8px;
  min-height: 360px; height: clamp(380px, 70vh, 900px);
  cursor: grab; user-select: none;
}
.img-container:active { cursor: grabbing; }
.svg-wrap :deep(svg) { display: block; max-width: none; }
.svg-wrap :deep([data-assurance-node-id]),
.svg-wrap :deep([data-assurance-edge-id]) { cursor: pointer; }
.svg-wrap :deep([data-assurance-node-id]:hover) rect,
.svg-wrap :deep([data-assurance-node-id]:hover) polygon,
.svg-wrap :deep([data-assurance-node-id]:hover) ellipse { stroke: #2563eb !important; stroke-width: 2 !important; }
.svg-wrap :deep([data-assurance-edge-id]:hover) path,
.svg-wrap :deep([data-assurance-edge-id]:hover) line,
.svg-wrap :deep([data-assurance-edge-id]:hover) polyline { stroke: #2563eb !important; stroke-width: 2 !important; }
/* The current selection stays marked while its detail panel is open, so the panel and the
   diagram always agree about what is being described. */
.svg-wrap :deep(.svg-assurance-selected) rect,
.svg-wrap :deep(.svg-assurance-selected) polygon,
.svg-wrap :deep(.svg-assurance-selected) ellipse { stroke: #2563eb !important; stroke-width: 3 !important; }
.svg-wrap :deep(.svg-assurance-selected) path,
.svg-wrap :deep(.svg-assurance-selected) line,
.svg-wrap :deep(.svg-assurance-selected) polyline { stroke: #2563eb !important; stroke-width: 2.5 !important; }
.svg-wrap :deep(.svg-assurance-selected) text { font-weight: 700; }
.reset-btn {
  position: absolute; top: 8px; right: 8px; padding: 4px 10px;
  background: rgba(255, 255, 255, .92); border: 1px solid #d1d5db;
  border-radius: 5px; font-size: 12px; cursor: pointer; color: #374151;
}
.reset-btn:hover { background: white; }
.zoom-hint {
  position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%);
  font-size: 11px; color: #9ca3af; background: rgba(255, 255, 255, .8);
  padding: 2px 8px; border-radius: 4px; pointer-events: none; white-space: nowrap;
}
.uca-matrix-wrap { overflow-x: auto; }
.uca-matrix { width: 100%; border-collapse: collapse; font-size: 12px; }
.uca-matrix th, .uca-matrix td { border: 1px solid #cbd5e1; padding: 8px; text-align: left; vertical-align: top; min-width: 130px; }
.uca-matrix thead th { background: #f1f5f9; }
.node-link { border: 0; background: none; padding: 0; color: #1d4ed8; cursor: pointer; font-weight: 600; text-align: left; }
.uca-chip { display: block; width: 100%; border: 1px solid #bfdbfe; border-radius: 5px; background: #eff6ff; color: #1e3a8a; padding: 6px; text-align: left; cursor: pointer; margin-bottom: 4px; }
.empty-cell, .empty-matrix { color: #94a3b8; }
.diagram-fallback { border: 1px solid #e2e8f0; border-radius: 6px; padding: 14px; background: #f8fafc; }
.fallback-note { margin: 0 0 12px; color: #64748b; font-size: 12px; }
.fallback-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.fallback-columns h3 { margin: 0 0 8px; font-size: 12px; text-transform: uppercase; color: #475569; }
.fallback-item { display: flex; flex-direction: column; gap: 2px; width: 100%; margin-bottom: 6px; padding: 8px; border: 1px solid #cbd5e1; border-radius: 5px; background: #fff; text-align: left; cursor: pointer; }
.fallback-item span { color: #64748b; font-size: 11px; }
.fallback-item--selected { border-color: #2563eb; background: #eff6ff; }
.puml-toggle { margin-top: 10px; }
.puml-toggle-btn { font-size: 12px; color: #6b7280; background: none; border: none; cursor: pointer; padding: 0; text-decoration: underline; }
.puml-source { font-size: 11px; background: #1e293b; color: #e2e8f0; padding: 12px; border-radius: 6px; overflow-x: auto; white-space: pre; margin: 8px 0 0; }
@media (max-width: 900px) {
  .fallback-columns { grid-template-columns: 1fr; }
}
</style>
