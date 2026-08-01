<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Effect, Exit } from 'effect'
import { modelServiceKey } from '../keys'
import type { DiagramContext, DiagramTypeUiConfig, EditableMetadataSpec } from '../../domain'
import type { RepoError } from '../../ports/ModelRepository'
import type { NotFoundError } from '../../domain'
import { useQuery } from '../composables/useQuery'
import { renderMatrixMarkdown } from '../lib/matrixMarkdown'
import type { C4Navigation } from '../../domain'
import { buildDrilldownByEntityId, c4NavigationOf, diagramNeedsSvg, matrixBodyOf } from './DiagramDetailView.helpers'
import { sanitizeDiagramSvg } from '../lib/svgSanitize'
import { useFittedPanZoom } from '../composables/useFittedPanZoom'
import { useDiagramSvgSelection } from '../composables/useDiagramSvgSelection'
import DiagramSplitLayout from '../components/DiagramSplitLayout.vue'
import DiagramDetailHeader from '../components/DiagramDetailHeader.vue'
import DiagramC4Navigation from '../components/DiagramC4Navigation.vue'
import DiagramEntitySidebar from '../components/DiagramEntitySidebar.vue'
import DiagramSyncPanel from '../components/DiagramSyncPanel.vue'
import DiagramDeletePanel from '../components/DiagramDeletePanel.vue'
import DiagramMatrixView from '../components/DiagramMatrixView.vue'

const svc = inject(modelServiceKey)!
const route = useRoute()
const router = useRouter()
const adminMode = ref(false)

const diagramId = computed(() => (route.query.id as string | undefined) ?? '')

const contextQuery = useQuery<DiagramContext, RepoError | NotFoundError>()
const svgQuery = useQuery<string, RepoError>()

const detail = computed(() => contextQuery.data.value?.diagram ?? null)
const c4Nav = computed<C4Navigation | null>(() => c4NavigationOf(contextQuery.data.value?.type_extras))
const drilldownByEntityId = computed(() => buildDrilldownByEntityId(c4Nav.value))
const diagramEntities = computed(() =>
  (contextQuery.data.value?.entities ?? [])
    .slice()
    .sort((a, b) => a.domain.localeCompare(b.domain) || a.artifact_type.localeCompare(b.artifact_type) || a.name.localeCompare(b.name))
)
const diagramConnections = computed(() => contextQuery.data.value?.connections ?? [])

const svgHtml = computed(() => svgQuery.data.value ? sanitizeDiagramSvg(svgQuery.data.value) : null)
const matrixHtml = computed(() => {
  const body = matrixBodyOf(detail.value?.type_extras)
  if (body === null || detail.value?.diagram_type !== 'matrix') return null
  return renderMatrixMarkdown(body)
})
const editPath = computed(() => detail.value?.diagram_type === 'matrix' ? '/diagram/edit/matrix' : '/diagram/edit')
const isGlobalDiagram = computed(() => detail.value?.is_global ?? false)

const showSource = ref(false)

const load = () => {
  if (!diagramId.value) return
  selection.selectedId.value = null
  contextQuery.reset()
  svgQuery.reset()
  contextQuery.run(svc.getDiagramContext(diagramId.value))
}

const selection = useDiagramSvgSelection({
  svc, router, svgHtml, detail, diagramEntities, diagramConnections, drilldownByEntityId, diagramId, reload: load,
})
// Template ref binding (`ref="svgContainer"`) requires a top-level `<script setup>` binding
// by that exact name — aliasing the composable's ref, not copying it.
const { svgContainer } = selection

const containerRef = ref<HTMLElement | null>(null)
const panZoom = useFittedPanZoom(containerRef, svgContainer)

const syncPanel = ref<InstanceType<typeof DiagramSyncPanel> | null>(null)
const deletePanel = ref<InstanceType<typeof DiagramDeletePanel> | null>(null)

onMounted(() => {
  void Effect.runPromiseExit(svc.getServerInfo()).then((exit) =>
    Exit.match(exit, { onSuccess: (info) => { adminMode.value = info.admin_mode }, onFailure: () => {} }),
  )
  load()
})

watch(svgHtml, (svg) => { if (svg) void panZoom.fitDiagramToViewport() })
watch(detail, (next) => {
  if (diagramNeedsSvg(next?.diagram_type)) svgQuery.run(svc.getDiagramSvg(diagramId.value))
})
watch(diagramId, load)

// The diagram type's editable-metadata config — the single source the sidebar's detail panels
// derive their editable fields from. Fetched once per diagram type; keyed by entity type so a
// panel resolves its own without the generic view knowing any type names.
const uiConfig = ref<DiagramTypeUiConfig | null>(null)
watch(detail, (next) => {
  if (!next) { uiConfig.value = null; return }
  void Effect.runPromise(svc.getDiagramTypeUiConfig(next.diagram_type))
    .then((config) => { uiConfig.value = config })
    .catch(() => { uiConfig.value = null })
})
const editableMetadataByType = computed<Record<string, EditableMetadataSpec>>(() => {
  const out: Record<string, EditableMetadataSpec> = {}
  for (const own of uiConfig.value?.diagram_only_types ?? []) {
    if (own.editable_metadata) out[own.entity_type] = own.editable_metadata
  }
  return out
})

const executeDelete = () => {
  void router.push(isGlobalDiagram.value ? { path: '/diagrams', query: { tier: 'enterprise' } } : '/diagrams')
}
</script>

<template>
  <div class="page">
    <DiagramDetailHeader
      v-if="detail"
      :detail="detail"
      :diagram-id="diagramId"
      :edit-path="editPath"
      :is-global-diagram="isGlobalDiagram"
      :admin-mode="adminMode"
      @sync="syncPanel?.requestSync()"
      @delete="deletePanel?.requestDelete()"
    />

    <div
      v-if="contextQuery.loading.value"
      class="state"
    >
      Loading…
    </div>
    <div
      v-else-if="contextQuery.errorMessage.value"
      class="state err"
    >
      {{ contextQuery.errorMessage.value }}
    </div>

    <template v-else-if="detail">
      <div class="meta">
        <span class="type-badge">{{ detail.diagram_type.replace('archimate-', '') }}</span>
        <span
          class="status-badge"
          :class="`status--${detail.status}`"
        >{{ detail.status }}</span>
        <span class="mono faded">v{{ detail.version }} · {{ detail.artifact_id }}</span>
      </div>

      <DiagramC4Navigation
        v-if="c4Nav"
        :c4-navigation="c4Nav"
      />

      <DiagramSplitLayout>
        <template #canvas>
          <DiagramMatrixView
            v-if="detail?.diagram_type === 'matrix' && matrixHtml"
            :html="matrixHtml"
          />
          <div
            v-else
            ref="containerRef"
            class="img-container"
            @mousedown="panZoom.onMouseDown"
            @dblclick="panZoom.resetView"
          >
            <div :style="panZoom.canvasStyle.value">
              <div
                v-if="svgQuery.loading.value"
                class="no-img"
              >
                Rendering SVG…
              </div>
              <div
                v-else-if="svgQuery.errorMessage.value"
                class="no-img err-txt"
              >
                {{ svgQuery.errorMessage.value }}
              </div>
              <div
                v-else-if="svgHtml"
                ref="svgContainer"
                class="svg-wrap"
                v-html="svgHtml"
              />
              <div
                v-else
                class="no-img"
              >
                No diagram rendered.
              </div>
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
              Scroll to zoom · Drag to pan · Click entity to inspect · Double-click to reset
            </div>
          </div>
        </template>

        <template #sidebar>
          <DiagramEntitySidebar
            :entities="diagramEntities"
            :viewer-extension="selection.viewerExtension.value"
            :selected-id="selection.selectedId.value"
            :selected-connection="selection.selectedConnection.value"
            :selected-sub-part="selection.selectedSubPart.value"
            :selected-entity-record="selection.selectedEntityRecord.value"
            :editable-metadata-by-type="editableMetadataByType"
            :selection-token="selection.selectionToken.value"
            :entity-query="selection.entityQuery"
            :edge-label-input="selection.edgeLabelInput.value"
            :edge-label-error="selection.edgeLabelMutation.errorMessage.value"
            :metadata-error="selection.metadataMutation.errorMessage.value"
            @select-entity="selection.selectEntity($event)"
            @clear-connection="selection.clearConnection()"
            @clear-sub-part="selection.clearSubPart()"
            @update:edge-label-input="selection.edgeLabelInput.value = $event"
            @save-edge-label="selection.saveEdgeLabel()"
            @sub-part-save="selection.patchEntityMetadata($event)"
            @entity-meta-save="selection.patchEntityMetadata($event)"
            @entity-edited="load"
          />
        </template>
      </DiagramSplitLayout>

      <DiagramSyncPanel
        v-if="!isGlobalDiagram"
        ref="syncPanel"
        :diagram-id="diagramId"
        @synced="load"
      />

      <DiagramDeletePanel
        v-if="!isGlobalDiagram || adminMode"
        ref="deletePanel"
        :diagram-id="diagramId"
        :is-global-diagram="isGlobalDiagram"
        :admin-mode="adminMode"
        @deleted="executeDelete"
      />

      <div
        v-if="detail.puml_source"
        class="src-row"
      >
        <button
          class="toggle-btn"
          @click="showSource = !showSource"
        >
          {{ showSource ? 'Hide' : 'Show' }} PUML source
        </button>
        <pre
          v-if="showSource"
          class="puml-src"
        >{{ detail.puml_source }}</pre>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 100%; }
.meta { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; font-size: 12px; }
.faded { color: #9ca3af; } .mono { font-family: monospace; }
.state { color: #6b7280; } .err { color: #dc2626; }
.type-badge { padding: 2px 8px; border-radius: 4px; font-size: 11px; background: #dbeafe; color: #1e40af; font-weight: 500; }

.img-container {
  position: relative; overflow: hidden; background: #f8fafc;
  border: 1px solid #e5e7eb; border-radius: 8px;
  min-height: 400px; height: clamp(420px, 78vh, 980px);
  cursor: grab; user-select: none;
}
@media (max-width: 800px) { .img-container { height: clamp(360px, 68vh, 820px); } }
.img-container:active { cursor: grabbing; }
.no-img { padding: 60px 40px; text-align: center; color: #9ca3af; font-size: 13px; }
.err-txt { color: #dc2626; }
.svg-wrap :deep(svg) { display: block; max-width: none; }
.svg-wrap :deep([data-entity-id]) { cursor: pointer; }
.svg-wrap :deep([data-entity-id]:hover) > :not(title) { opacity: 0.85; }
.svg-wrap :deep([data-entity-id]:hover) polygon,
.svg-wrap :deep([data-entity-id]:hover) rect,
.svg-wrap :deep([data-entity-id]:hover) polyline,
.svg-wrap :deep([data-entity-id]:hover) ellipse { stroke: #2563eb !important; stroke-width: 2 !important; }
.svg-wrap :deep(.svg-selected) polygon,
.svg-wrap :deep(.svg-selected) rect,
.svg-wrap :deep(.svg-selected) polyline,
.svg-wrap :deep(.svg-selected) ellipse { stroke: #2563eb !important; stroke-width: 2.5 !important; }
/* Sentinel-link representatives (activity diagrams) wrap only a <text> node, with no
   polygon/rect/polyline/ellipse child for the rules above to match. */
.svg-wrap :deep(a[data-entity-id]:hover) text { fill: #2563eb !important; }
.svg-wrap :deep(a.svg-selected) text { fill: #2563eb !important; font-weight: 700; }
/* Bare-shape representatives (an activity step's own rect/polygon) — the descendant rules
   above can't match the element itself. */
.svg-wrap :deep(rect[data-entity-id]:hover),
.svg-wrap :deep(polygon[data-entity-id]:hover) { stroke: #2563eb !important; stroke-width: 2 !important; }
.svg-wrap :deep(rect.svg-selected),
.svg-wrap :deep(polygon.svg-selected) { stroke: #2563eb !important; stroke-width: 2.5 !important; }
.svg-wrap :deep([data-subpart]) { cursor: pointer; }
.svg-wrap :deep(text[data-subpart]:hover) { fill: #2563eb !important; }
.svg-wrap :deep(g[data-subpart]:hover) ellipse { stroke: #2563eb !important; }
.svg-wrap :deep(text.svg-subpart-selected) { fill: #2563eb !important; font-weight: 700; }
.svg-wrap :deep(.svg-subpart-selected) ellipse { stroke: #2563eb !important; stroke-width: 2 !important; }
.svg-wrap :deep([data-conn-id]) { cursor: pointer; }
.svg-wrap :deep([data-conn-id]:hover) path,
.svg-wrap :deep([data-conn-id]:hover) polygon,
.svg-wrap :deep([data-conn-id]:hover) line,
.svg-wrap :deep([data-conn-id]:hover) polyline { stroke: #2563eb !important; stroke-width: 2 !important; }
.svg-wrap :deep(.svg-conn-selected) path,
.svg-wrap :deep(.svg-conn-selected) polygon,
.svg-wrap :deep(.svg-conn-selected) line,
.svg-wrap :deep(.svg-conn-selected) polyline { stroke: #2563eb !important; stroke-width: 2.5 !important; }
.reset-btn { position: absolute; top: 8px; right: 8px; padding: 4px 10px; background: rgba(255,255,255,.92); border: 1px solid #d1d5db; border-radius: 5px; font-size: 12px; cursor: pointer; color: #374151; }
.reset-btn:hover { background: white; }
.zoom-hint { position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%); font-size: 11px; color: #9ca3af; background: rgba(255,255,255,.8); padding: 2px 8px; border-radius: 4px; pointer-events: none; white-space: nowrap; }

.src-row { margin-top: 16px; }
.toggle-btn { padding: 5px 14px; border-radius: 6px; border: 1px solid #d1d5db; background: white; font-size: 13px; cursor: pointer; color: #374151; margin-bottom: 8px; } .toggle-btn:hover { background: #f9fafb; }
.puml-src { background: #1e293b; color: #e2e8f0; padding: 16px; border-radius: 8px; font-size: 12px; line-height: 1.5; overflow-x: auto; white-space: pre; }
</style>
