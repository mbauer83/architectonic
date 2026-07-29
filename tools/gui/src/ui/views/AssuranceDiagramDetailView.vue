<script setup lang="ts">
/**
 * One assurance projection at full size, with the selected node's or edge's detail beside it.
 *
 * The split mirrors the architecture area's diagram detail: the same resizable layout component,
 * and the same rule that the canvas keeps the whole width until the reader selects something —
 * a permanently reserved, usually empty sidebar just makes the diagram smaller for no reason.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AssuranceDiagramPanel from '../components/AssuranceDiagramPanel.vue'
import FmeaMatrixPanel from '../components/FmeaMatrixPanel.vue'
import AssuranceNodeDetail from '../components/AssuranceNodeDetail.vue'
import DiagramSplitLayout from '../components/DiagramSplitLayout.vue'
import type { AssuranceDiagramEdge, AssuranceDiagramNode } from '../components/AssuranceDiagramPanel.helpers'
import {
  fetchAssuranceDiagrams,
  findDiagram,
  type AssuranceDiagramMeta,
} from '../lib/assuranceDiagrams'

const route = useRoute()

const diagrams = ref<AssuranceDiagramMeta[]>([])
const catalogError = ref<string | null>(null)
const nodeNames = ref(new Map<string, string>())

const selectedNodeId = ref<string | null>(null)
const selectedEdge = ref<AssuranceDiagramEdge | null>(null)

/** A projection is identified by its analysis *and* its type — there is one control structure per
 * STPA and one matrix per FMEA, so the type alone names no particular drawing. */
const queryValue = (key: string): string | null => {
  const raw = route.query[key]
  return typeof raw === 'string' && raw.length > 0 ? raw : null
}

const analysisId = computed(() => queryValue('analysis'))
const diagramType = computed(() => queryValue('type'))

/**
 * The failure-mode grid is built client-side from its own endpoint, not from a rendered projection.
 *
 * So it gets the real grid here rather than the SVG panel, which had no PUML to draw and reported
 * "diagram rendering is unavailable" — technically true and completely unhelpful, since nothing was
 * ever going to render. The type declares itself store-projected so it appears in the catalog; how
 * it is *drawn* is this surface's business.
 */
const isFmeaMatrix = computed(() => diagramType.value === 'fmea-matrix')
const meta = computed(() => findDiagram(diagrams.value, analysisId.value, diagramType.value))
const hasSelection = computed(() => selectedNodeId.value !== null || selectedEdge.value !== null)

const edgeKey = (edge: AssuranceDiagramEdge): string =>
  edge.edge_id ?? `${edge.source_id}:${edge.target_id}`
const selectedEdgeId = computed(() => selectedEdge.value ? edgeKey(selectedEdge.value) : null)

/** Clicking the current selection again clears it, giving the canvas its full width back. */
function selectNode(nodeId: string) {
  selectedEdge.value = null
  selectedNodeId.value = selectedNodeId.value === nodeId ? null : nodeId
}

function selectEdge(edge: AssuranceDiagramEdge) {
  selectedNodeId.value = null
  selectedEdge.value = selectedEdgeId.value === edgeKey(edge) ? null : edge
}

function clearSelection() {
  selectedNodeId.value = null
  selectedEdge.value = null
}

function onProjectionLoaded(projection: { nodes: AssuranceDiagramNode[]; edges: AssuranceDiagramEdge[] }) {
  nodeNames.value = new Map(projection.nodes.map((node) => [node.node_id, node.name]))
  clearSelection()
}

const nodeLabel = (nodeId: string) => nodeNames.value.get(nodeId) ?? nodeId

onMounted(async () => {
  const catalog = await fetchAssuranceDiagrams()
  diagrams.value = catalog.diagrams
  catalogError.value = catalog.error
})

watch([analysisId, diagramType], clearSelection)
</script>

<template>
  <div class="detail-page">
    <div class="detail-header">
      <RouterLink
        to="/assurance/diagrams"
        class="back-link"
      >
        ← Assurance diagrams
      </RouterLink>
      <h1 class="detail-title">
        {{ meta ? `${meta.type_label} — ${meta.title}` : (diagramType ?? 'Assurance diagram') }}
      </h1>
      <p
        v-if="meta?.description"
        class="detail-subtitle"
      >
        {{ meta.description }}
      </p>
    </div>

    <p
      v-if="catalogError"
      class="state-error"
    >
      {{ catalogError }}
    </p>
    <p
      v-else-if="!analysisId || !diagramType"
      class="state-msg"
    >
      No diagram selected. Pick one from the assurance diagrams overview.
    </p>
    <p
      v-else-if="diagrams.length > 0 && !meta"
      class="state-msg"
    >
      No "{{ diagramType }}" projection for analysis {{ analysisId }} — the analysis may be gone,
      or its method may not draw this diagram.
    </p>

    <DiagramSplitLayout
      v-else
      :sidebar-collapsed="!hasSelection"
    >
      <template #canvas>
        <FmeaMatrixPanel
          v-if="isFmeaMatrix"
          :analysis-id="analysisId"
        />
        <AssuranceDiagramPanel
          v-else
          :analysis-id="analysisId"
          :diagram-type="diagramType"
          :selected-node-id="selectedNodeId"
          :selected-edge-id="selectedEdgeId"
          @select-node="selectNode"
          @select-edge="selectEdge"
          @loaded="onProjectionLoaded"
        />
      </template>

      <template #sidebar>
        <aside class="selection-panel">
          <template v-if="selectedNodeId">
            <AssuranceNodeDetail
              :node-id="selectedNodeId"
              @close="clearSelection"
            />
            <RouterLink
              class="edit-node-link"
              :to="`/assurance/node/${encodeURIComponent(selectedNodeId)}`"
            >
              Edit in Assurance Browse →
            </RouterLink>
          </template>
          <div
            v-else-if="selectedEdge"
            class="edge-detail"
          >
            <div class="edge-detail__header">
              <strong>{{ selectedEdge.conn_type }}</strong>
              <button
                aria-label="Close"
                @click="clearSelection"
              >
                ×
              </button>
            </div>
            <p>{{ nodeLabel(selectedEdge.source_id) }} → {{ nodeLabel(selectedEdge.target_id) }}</p>
            <p v-if="selectedEdge.label || selectedEdge.name">
              {{ selectedEdge.label || selectedEdge.name }}
            </p>
            <div class="edge-actions">
              <RouterLink :to="`/assurance/node/${encodeURIComponent(selectedEdge.source_id)}`">
                Edit source
              </RouterLink>
              <RouterLink :to="`/assurance/node/${encodeURIComponent(selectedEdge.target_id)}`">
                Edit target
              </RouterLink>
            </div>
          </div>
        </aside>
      </template>
    </DiagramSplitLayout>
  </div>
</template>

<style scoped>
.detail-page { max-width: 100%; padding: 24px 24px 32px; }
.detail-header { margin-bottom: 18px; }
.back-link { font-size: 13px; color: #64748b; display: block; margin-bottom: 12px; }
.detail-title { font-size: 20px; font-weight: 700; margin: 0; }
.detail-subtitle { color: #64748b; font-size: 13px; margin: 6px 0 0; }
.state-msg { color: #64748b; font-size: 14px; }
.state-error { color: #dc2626; font-size: 14px; }

.selection-panel {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
  position: sticky;
  top: 16px;
  max-height: clamp(420px, 78vh, 980px);
  overflow-y: auto;
}
.edit-node-link { display: block; padding: 0 16px 16px; font-size: 12px; color: #1d4ed8; }
.edge-detail { padding: 16px; font-size: 13px; }
.edge-detail__header { display: flex; justify-content: space-between; }
.edge-detail__header button { border: 0; background: none; cursor: pointer; font-size: 18px; }
.edge-actions { display: flex; gap: 12px; margin-top: 8px; }
</style>
