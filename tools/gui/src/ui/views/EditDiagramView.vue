<script setup lang="ts">
import { inject, ref, computed, onMounted, useTemplateRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Effect, Exit } from 'effect'
import { modelServiceKey, toastKey } from '../keys'
import type {
  DiagramContext, DiagramPreviewResult, WriteResult,
  DiagramTypeUiConfig, ViewpointSummary, ViewpointProjection,
} from '../../domain'
import type { RepoError } from '../../ports/ModelRepository'
import type { NotFoundError } from '../../domain'
import DiagramEditHeader from '../components/DiagramEditHeader.vue'
import DiagramEditViewpointBar from '../components/DiagramEditViewpointBar.vue'
import DiagramEditSidebar from '../components/DiagramEditSidebar.vue'
import DiagramPreviewPanel from '../components/DiagramPreviewPanel.vue'
import { findViewpointBySlug } from '../components/ViewpointSelect.helpers'
import { useQuery } from '../composables/useQuery'
import { useMutation } from '../composables/useMutation'
import { usePanZoom } from '../composables/usePanZoom'
import { useDiagramEditSelection } from '../composables/useDiagramEditSelection'
import { useDiagramEditSvgOverlay } from '../composables/useDiagramEditSvgOverlay'
import { sanitizeDiagramSvg } from '../lib/svgSanitize'
import { loadViewpointSummaries } from '../lib/viewpointSummary'

const svc = inject(modelServiceKey)!
const addToast = inject(toastKey)!
const route = useRoute()
const router = useRouter()

const diagramId = computed(() => (route.query.id as string | undefined) ?? '')

const contextQuery = useQuery<DiagramContext, RepoError | NotFoundError>()
const svgQuery = useQuery<string, RepoError>()
const previewMutation = useMutation<DiagramPreviewResult, RepoError>()
const saveMutation = useMutation<WriteResult, RepoError>()

const diagramDetail = computed(() => contextQuery.data.value?.diagram ?? null)
const diagramType = computed(() => diagramDetail.value?.diagram_type)
const uiConfig = ref<DiagramTypeUiConfig | null>(null)

// ── Viewpoint selector + ghost/hide overlay ─────────────────────────────────

const viewpoints = ref<ViewpointSummary[]>([])
const viewpointSlug = ref<string | null>(null)
const viewpointPinnedVersion = ref<number | null>(null)
const viewpointProjection = ref<ViewpointProjection | null>(null)
const hideInsteadOfGhost = ref(false)

const loadViewpoints = async () => {
  viewpoints.value = await loadViewpointSummaries(svc.listViewpointDefinitions())
}

const loadProjection = async () => {
  if (!diagramId.value) return
  viewpointProjection.value = await Effect.runPromise(svc.getViewpointProjection(diagramId.value)).catch(() => null)
}

const onSelectViewpoint = (viewpoint: ViewpointSummary | null) => {
  viewpointPinnedVersion.value = viewpoint?.version ?? null
  void selection.refreshDiscovery()
}

const currentDefinitionVersion = computed(
  () => findViewpointBySlug(viewpoints.value, viewpointSlug.value)?.version ?? null,
)
const stalePin = computed(() => viewpointProjection.value?.stale_pin === true)

const doRePin = () => {
  if (currentDefinitionVersion.value !== null) viewpointPinnedVersion.value = currentDefinitionVersion.value
}

const dismissViewpoint = () => {
  viewpointSlug.value = null
  viewpointPinnedVersion.value = null
  void selection.refreshDiscovery()
}

// ── Diagram-type-owned entity data ──────────────────────────────────────────

const baseTypeEntityData = ref<Record<string, unknown>>({})
const typeEntityPatch = ref<Record<string, unknown>>({})
const typeEntityData = computed(() => ({ ...baseTypeEntityData.value, ...typeEntityPatch.value }))
const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
const mergeTypeEntityData = (patch: Record<string, unknown>) => {
  typeEntityPatch.value = { ...typeEntityPatch.value, ...patch }
  previewMutation.reset()
}
const setTypeEntityData = (next: Record<string, unknown>) => {
  baseTypeEntityData.value = next
  typeEntityPatch.value = {}
  previewMutation.reset()
}

watch(diagramDetail, (d) => {
  if (d?.diagram_type === 'matrix') {
    void router.replace({ path: '/diagram/edit/matrix', query: { id: diagramId.value } })
  }
})
const svgHtml = computed(() => svgQuery.data.value ? sanitizeDiagramSvg(svgQuery.data.value) : null)
const saveError = computed(() => {
  const r = saveMutation.result.value
  if (r && !r.wrote) return r.content ?? 'Verification failed'
  return saveMutation.errorMessage.value
})

// ── Pan / Zoom ────────────────────────────────────────────────────────────────

const viewport = useTemplateRef<HTMLElement>('viewport')
const { canvasStyle, isTransformed, resetView, startDrag } = usePanZoom(viewport)
const onMouseDown = (e: MouseEvent) => {
  if ((e.target as HTMLElement).closest('[data-entity-id],[data-conn-id],button,a,input,label')) return
  startDrag(e)
}

// ── Selection + SVG overlay ──────────────────────────────────────────────────

const selection = useDiagramEditSelection({ svc, diagramType, viewpointSlug })
const svgContainer = useTemplateRef<HTMLElement>('svgContainer')
useDiagramEditSvgOverlay({
  svgContainer,
  svgHtml,
  diagramType,
  diagramEntities: selection.diagramEntities,
  diagramConnections: selection.diagramConnections,
  typeEntityData,
  toRemoveEntityIds: selection.toRemoveEntityIds,
  toRemoveConnIds: selection.toRemoveConnIds,
  selectedNewConnIds: selection.selectedNewConnIds,
  isConnIncluded: selection.isConnIncluded,
  includedConnIds: selection.includedConnIds,
  viewpointProjection,
  hideInsteadOfGhost,
  toggleEntityRemoval: selection.toggleEntityRemoval,
  toggleConn: selection.toggleConn,
})

// ── Load ──────────────────────────────────────────────────────────────────────

const load = async () => {
  if (!diagramId.value) return
  selection.reset()
  previewMutation.reset(); saveMutation.reset()

  contextQuery.run(svc.getDiagramContext(diagramId.value))
  svgQuery.run(svc.getDiagramSvg(diagramId.value))

  const exit = await Effect.runPromiseExit(svc.getDiagramContext(diagramId.value))
  Exit.match(exit, {
    onSuccess: (context) => {
      selection.populateFromContext(context)
      baseTypeEntityData.value = asRecord(context.diagram.diagram_entities)
      typeEntityPatch.value = {}
      viewpointSlug.value = context.diagram.viewpoint?.slug ?? null
      viewpointPinnedVersion.value = context.diagram.viewpoint?.version ?? null
      void Effect.runPromise(svc.getDiagramTypeUiConfig(context.diagram.diagram_type))
        .then((config) => { uiConfig.value = config })
        .catch(() => { uiConfig.value = null })
      void selection.refreshDiscovery()
      void loadProjection()
    },
    onFailure: () => {},
  })
}

onMounted(() => { void load(); void loadViewpoints() })
watch(diagramId, load)

// ── Preview / Save ────────────────────────────────────────────────────────────

const finalEntityIds = computed(() => {
  const base = [
    ...selection.includedEntities.value.filter((e) => !selection.toRemoveEntityIds.value.has(e.artifact_id)).map((e) => e.artifact_id),
    ...selection.entitiesToAdd.value.map((e) => e.artifact_id),
  ]
  const mapped = (typeEntityData.value.entity_ids_mapped as string[] | undefined) ?? []
  return [...new Set([...base, ...mapped])]
})

const doPreview = () => {
  if (!diagramDetail.value) return
  void previewMutation.run(svc.previewDiagram({
    diagram_type: diagramDetail.value.diagram_type,
    name: diagramDetail.value.name,
    entity_ids: finalEntityIds.value,
    connection_ids: selection.finalConnIds.value,
    diagram_entities: typeEntityData.value,
  }))
}

const doSave = async () => {
  if (!diagramDetail.value) return
  const exit = await saveMutation.run(svc.editDiagram({
    artifact_id: diagramId.value,
    diagram_type: diagramDetail.value.diagram_type,
    name: diagramDetail.value.name,
    entity_ids: finalEntityIds.value,
    connection_ids: selection.finalConnIds.value,
    diagram_entities: typeEntityData.value,
    viewpoint: viewpointSlug.value
      ? { slug: viewpointSlug.value, version: viewpointPinnedVersion.value ?? currentDefinitionVersion.value ?? 1 }
      : null,
    dry_run: false,
  }))
  if (!Exit.isSuccess(exit) || !exit.value.wrote) return
  addToast('Diagram saved')
  void router.push({ path: '/diagram', query: { id: diagramId.value } })
}

const saveDisabled = computed(() => saveMutation.running.value || !previewMutation.result.value || !diagramDetail.value)
const saveTitle = computed(() => !previewMutation.result.value ? 'Run Preview first' : '')
</script>

<template>
  <div class="page">
    <DiagramEditHeader
      :diagram-name="diagramDetail?.name ?? null"
      :diagram-type-label="diagramDetail ? diagramDetail.diagram_type.replace('archimate-', '') : null"
      :loading="contextQuery.loading.value"
      :preview-running="previewMutation.running.value"
      :preview-disabled="previewMutation.running.value || !diagramDetail"
      :save-running="saveMutation.running.value"
      :save-disabled="saveDisabled"
      :save-title="saveTitle"
      @back="router.push({ path: '/diagram', query: { id: diagramId } })"
      @preview="doPreview"
      @save="doSave"
    />

    <DiagramEditViewpointBar
      :viewpoints="viewpoints"
      :viewpoint-slug="viewpointSlug"
      :viewpoint-pinned-version="viewpointPinnedVersion"
      :stale-pin="stalePin"
      :hide-instead-of-ghost="hideInsteadOfGhost"
      @dismiss="dismissViewpoint"
      @repin="doRePin"
      @update:hide-instead-of-ghost="hideInsteadOfGhost = $event"
    />

    <div class="main-grid">
      <div
        ref="viewport"
        class="img-container"
        @mousedown="onMouseDown"
        @dblclick="resetView"
      >
        <div :style="canvasStyle">
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
          v-if="isTransformed"
          class="reset-btn"
          @click.stop="resetView"
        >
          ⊙ Reset
        </button>
        <div class="zoom-hint">
          Click entity to mark for removal · Click connection to toggle · Scroll/drag to navigate
        </div>
      </div>

      <DiagramEditSidebar
        :viewpoints="viewpoints"
        :viewpoint-slug="viewpointSlug"
        :ui-config="uiConfig"
        :diagram-type="diagramType"
        :effective-entity-ids="selection.effectiveEntityIds.value"
        :type-entity-data="typeEntityData"
        :effective-entities-list="selection.effectiveEntitiesList.value"
        :diagram-connections="selection.diagramConnections.value"
        :diagram-id="diagramId"
        :selection-rows="selection.selectionRows.value"
        :candidate-connections="[...selection.allModelConns.value.values()]"
        :final-conn-ids="selection.finalConnIds.value"
        :related-entities-by-id="selection.relatedEntitiesById.value"
        :expanded-connection-entity-ids="[...selection.expandedConnectionEntityIds.value]"
        :expanded-related-entity-ids="[...selection.expandedRelatedEntityIds.value]"
        :to-remove-entities="selection.toRemoveEntities.value"
        :preview-running="previewMutation.running.value"
        :preview-disabled="previewMutation.running.value || !diagramDetail"
        :save-running="saveMutation.running.value"
        :save-disabled="saveDisabled"
        :save-title="saveTitle"
        :save-error="saveError"
        @update:viewpoint-slug="viewpointSlug = $event"
        @select-viewpoint="onSelectViewpoint"
        @add-entity="selection.addEntity($event)"
        @diagram-entities-change="mergeTypeEntityData"
        @diagram-connections-change="selection.diagramConnections.value = $event"
        @occurrence-change="setTypeEntityData"
        @toggle-connections="selection.toggleConnections($event)"
        @toggle-related="selection.toggleRelated($event)"
        @toggle-connection="selection.toggleConn($event)"
        @entity-action="selection.handleEntityAction($event)"
        @restore-entity="selection.toggleEntityRemoval($event)"
        @preview="doPreview"
        @save="doSave"
      />
    </div>

    <DiagramPreviewPanel
      :running="previewMutation.running.value"
      :error-message="previewMutation.errorMessage.value"
      :result="previewMutation.result.value"
    />
  </div>
</template>

<style scoped>
.page { max-width: 100%; }
.main-grid { display: grid; grid-template-columns: 1fr 50%; gap: 16px; align-items: start; }
@media (max-width: 860px) { .main-grid { grid-template-columns: 1fr; } }

.img-container {
  position: relative; overflow: hidden; background: #f8fafc;
  border: 1px solid #e5e7eb; border-radius: 8px; min-height: 500px;
  cursor: grab; user-select: none;
}
.img-container:active { cursor: grabbing; }
.no-img { padding: 60px 40px; text-align: center; color: #9ca3af; font-size: 13px; }
.err-txt { color: #dc2626; }

.svg-wrap :deep(svg) { display: block; max-width: none; }
.svg-wrap :deep([data-entity-id]) { cursor: pointer; }
.svg-wrap :deep([data-entity-id]:hover) polygon,
.svg-wrap :deep([data-entity-id]:hover) rect { stroke: #ef4444 !important; stroke-width: 2 !important; }
.svg-wrap :deep(a[data-entity-id]:hover) text { fill: #ef4444 !important; }
.svg-wrap :deep(rect[data-entity-id]:hover),
.svg-wrap :deep(polygon[data-entity-id]:hover) { stroke: #ef4444 !important; stroke-width: 2 !important; }
.svg-wrap :deep(.svg-remove) { opacity: 0.4; }
.svg-wrap :deep(.svg-remove) polygon,
.svg-wrap :deep(.svg-remove) rect,
.svg-wrap :deep(.svg-remove) path { stroke: #ef4444 !important; stroke-width: 2.5 !important; }
.svg-wrap :deep([data-conn-id]) { cursor: pointer; }
.svg-wrap :deep([data-conn-id]:hover) path,
.svg-wrap :deep([data-conn-id]:hover) polygon { stroke: #6366f1 !important; stroke-width: 2 !important; }
.svg-wrap :deep(.svg-viewpoint-ghosted) { opacity: 0.3; filter: grayscale(60%); }
.svg-wrap :deep(.svg-viewpoint-hidden) { display: none; }

.reset-btn { position: absolute; top: 8px; right: 8px; padding: 4px 10px; background: rgba(255,255,255,.92); border: 1px solid #d1d5db; border-radius: 5px; font-size: 12px; cursor: pointer; color: #374151; }
.reset-btn:hover { background: white; }
.zoom-hint { position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%); font-size: 11px; color: #9ca3af; background: rgba(255,255,255,.8); padding: 2px 8px; border-radius: 4px; pointer-events: none; white-space: nowrap; }
</style>
