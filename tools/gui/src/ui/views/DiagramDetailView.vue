<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Effect, Exit } from 'effect'
import { modelServiceKey, toastKey } from '../keys'
import type { DiagramContext, EditableMetadataSpec } from '../../domain'
import type { RepoError } from '../../ports/ModelRepository'
import type { NotFoundError } from '../../domain'
import { useQuery } from '../composables/useQuery'
import { useDiagramTypeUiConfig } from '../composables/useDiagramTypeUiConfig'
import { renderMatrixMarkdown } from '../lib/matrixMarkdown'
import type { C4Navigation } from '../../domain'
import {
  buildDrilldownByEntityId, c4NavigationOf, diagramNeedsSvg, editRouteFor, editsOnCanvas,
  editableMetadataByEntityType, isADifferentDiagram, matrixHtmlOf,
} from './DiagramDetailView.helpers'
import DrilldownMenu from '../components/DrilldownMenu.vue'
import DiagramReadingPanel from '../components/DiagramReadingPanel.vue'
import { useDiagramReadingLens } from '../composables/useDiagramReadingLens'
import { useFittedPanZoom } from '../composables/useFittedPanZoom'
import { useFullscreen } from '../composables/useFullscreen'
import DiagramViewportControls from '../components/DiagramViewportControls.vue'
import { useDiagramSvgSelection } from '../composables/useDiagramSvgSelection'
import DiagramSplitLayout from '../components/DiagramSplitLayout.vue'
import DiagramDetailHeader from '../components/DiagramDetailHeader.vue'
import DiagramC4Navigation from '../components/DiagramC4Navigation.vue'
import DiagramEntitySidebar from '../components/DiagramEntitySidebar.vue'
import FullscreenDock from '../components/FullscreenDock.vue'
import DiagramSyncPanel from '../components/DiagramSyncPanel.vue'
import DiagramDeletePanel from '../components/DiagramDeletePanel.vue'
import DiagramOwnIcons from '../components/DiagramOwnIcons.vue'
import DiagramMatrixView from '../components/DiagramMatrixView.vue'
import { diagramEditRoute, matrixEditRoute } from '../router/artifactRoutes'
import DiagramEditBar from '../components/DiagramEditBar.vue'
import LayoutLabCanvas from '../components/layoutLab/LayoutLabCanvas.vue'
import type { CanvasHandle, EditBarHandle } from '../composables/useDiagramEditMode'
import { useDiagramEditMode } from '../composables/useDiagramEditMode'

const svc = inject(modelServiceKey)!
const toast = inject(toastKey, () => undefined)
const route = useRoute()
const router = useRouter()
const adminMode = ref(false)

const diagramId = computed(() => route.params.artifactId as string)

const contextQuery = useQuery<DiagramContext, RepoError | NotFoundError>()
// This diagram's picture and how it is being read: the lens, the offer, and the render.
const reading = useDiagramReadingLens({
  svc, diagramId, drawn: () => diagramNeedsSvg(detail.value?.diagram_type),
})
const { lens, svgHtml } = reading

const detail = computed(() => contextQuery.data.value?.diagram ?? null)
const c4Nav = computed<C4Navigation | null>(() => c4NavigationOf(contextQuery.data.value?.type_extras))
const drilldownByEntityId = computed(() => buildDrilldownByEntityId(c4Nav.value))
const diagramEntities = computed(() =>
  (contextQuery.data.value?.entities ?? [])
    .slice()
    .sort((a, b) => a.domain.localeCompare(b.domain) || a.artifact_type.localeCompare(b.artifact_type) || a.name.localeCompare(b.name))
)
const diagramConnections = computed(() => contextQuery.data.value?.connections ?? [])

const matrixHtml = computed(() =>
  matrixHtmlOf(detail.value?.diagram_type, detail.value?.type_extras, renderMatrixMarkdown))
const editPath = computed(() =>
  editRouteFor(detail.value?.diagram_type, diagramId.value, matrixEditRoute, diagramEditRoute))
const isGlobalDiagram = computed(() => detail.value?.is_global ?? false)

const showSource = ref(false)

// The diagram the query currently holds, so a reload can tell a refresh from a fresh load.
let loadedDiagramId: string | null = null

const load = () => {
  if (!diagramId.value) return
  if (isADifferentDiagram(loadedDiagramId, diagramId.value)) {
    selection.selectedId.value = null
    contextQuery.reset()
    reading.reset()
  }
  loadedDiagramId = diagramId.value
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
const fullscreen = useFullscreen(containerRef)
// Entering or leaving fullscreen is a framing request: re-fit even when the view has been
// transformed, since the whole point of the gesture is to see the diagram against the new space.
watch(fullscreen.isFullscreen, () => { void panZoom.fitDiagramToViewport() })

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
  if (!diagramNeedsSvg(next?.diagram_type)) return
  reading.begin()
})
watch(diagramId, load)

// The diagram type's editable-metadata config — the single source the sidebar's detail panels
// derive their editable fields from. Fetched once per diagram type; keyed by entity type so a
// panel resolves its own without the generic view knowing any type names.
const uiConfig = useDiagramTypeUiConfig(svc, computed(() => detail.value?.diagram_type))
const editableMetadataByType = computed<Record<string, EditableMetadataSpec>>(() =>
  editableMetadataByEntityType(uiConfig.value))

// Edit mode: the same page, the canvas in place of the picture (D15). Leaving reloads the picture,
// which the server has drawn again from whatever was saved.
const editCanvas = ref<CanvasHandle | null>(null)
const editBar = ref<EditBarHandle | null>(null)
const edit = useDiagramEditMode(svc, diagramId, { canvas: editCanvas, bar: editBar }, load, toast)
const editing = computed(() => edit.active.value)
watch(editing, () => { void panZoom.fitDiagramToViewport() })
watch(() => edit.session.geometry.value, () => { if (editing.value) void panZoom.fitDiagramToViewport() })

const executeDelete = () => {
  void router.push(isGlobalDiagram.value ? { path: '/diagrams', query: { tier: 'enterprise' } } : '/diagrams')
}
</script>

<template>
  <div class="page">
    <!-- The browser paints nothing outside a fullscreen element, so a menu living in the page
         layout simply vanishes on entry. `FullscreenDock` moves it inside the canvas instead —
         the same fact and the same fix the sidebar and the toolbar already face. -->
    <FullscreenDock
      :fullscreen-host="containerRef"
      :is-fullscreen="fullscreen.isFullscreen.value"
      :revealed="true"
    >
      <DrilldownMenu
        v-if="selection.drilldownChoice.value"
        :targets="selection.drilldownChoice.value.targets"
        :x="selection.drilldownChoice.value.x"
        :y="selection.drilldownChoice.value.y"
        :scope-name="selection.drilldownChoice.value.nodeName"
        @choose="selection.chooseDrilldown"
        @dismiss="selection.drilldownChoice.value = null"
      />
    </FullscreenDock>
    <DiagramDetailHeader
      v-if="detail"
      :detail="detail"
      :diagram-id="diagramId"
      :edit-path="editPath"
      :is-global-diagram="isGlobalDiagram"
      :admin-mode="adminMode"
      :lens="lens"
      :edits-on-canvas="editsOnCanvas(detail)"
      :editing="editing"
      @sync="syncPanel?.requestSync()"
      @delete="deletePanel?.requestDelete()"
      @edit="edit.enter()"
      @done="edit.done()"
    />

    <!-- Only while there is nothing to show. A refresh keeps the rendered canvas mounted, because
         replacing it detaches the browser's fullscreen element and drops the reader out of it. -->
    <div
      v-if="contextQuery.loading.value && !detail"
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
        <span
          v-if="editing"
          class="editing-note"
          data-testid="editing-note"
        >Editing — nothing is saved until you press Save · <em>Done</em> or <kbd>Esc</kbd> leaves</span>
      </div>

      <DiagramEditBar
        v-if="editing"
        ref="editBar"
        :edit="edit"
      />

      <DiagramC4Navigation
        v-if="c4Nav"
        :c4-navigation="c4Nav"
      />

      <DiagramReadingPanel
        v-if="!editing && diagramNeedsSvg(detail.diagram_type) && reading.offersAnything.value"
        class="reading-panel"
        :panel="reading.panel.value"
        :lens="lens"
        :busy="reading.adjusting.value"
        @update:lens="lens = $event"
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
            class="img-container viewport-host"
            :class="{ editing, panning: edit.spaceHeld.value }"
            :data-mode="editing ? 'edit' : 'view'"
            data-testid="diagram-canvas-host"
            @mousedown="editing ? edit.panPress($event, panZoom.onMouseDown) : panZoom.onMouseDown($event)"
            @dblclick="editing || panZoom.resetView()"
          >
            <div
              class="pan-canvas"
              :style="panZoom.canvasStyle.value"
            >
              <div
                v-if="editing"
                ref="svgContainer"
                class="svg-wrap"
              >
                <LayoutLabCanvas
                  ref="editCanvas"
                  :session="edit.session"
                />
              </div>
              <div
                v-else-if="reading.loading.value"
                class="no-img"
              >
                Rendering SVG…
              </div>
              <div
                v-else-if="reading.errorMessage.value"
                class="no-img err-txt"
              >
                {{ reading.errorMessage.value }}
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
            <DiagramViewportControls
              :is-transformed="panZoom.isTransformed.value"
              :is-fullscreen="fullscreen.isFullscreen.value"
              :can-fullscreen="fullscreen.isSupported"
              :hint="editing
                ? 'Drag an element or a box by its title to move it · drag a handle to resize · Space+drag pans'
                : 'Scroll to zoom · Drag to pan · Click entity to inspect · Double-click to reset'"
              @reset="panZoom.resetView"
              @toggle-fullscreen="fullscreen.toggle"
            />
          </div>
        </template>

        <template #sidebar>
          <FullscreenDock
            :fullscreen-host="containerRef"
            :is-fullscreen="fullscreen.isFullscreen.value"
            :revealed="selection.hasSelection.value"
          >
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
              @entity-edited="selection.entityEdited()"
            />
          </FullscreenDock>
        </template>
      </DiagramSplitLayout>

      <DiagramOwnIcons
        v-if="!isGlobalDiagram && detail"
        :diagram-id="diagramId"
        :diagram-entities="detail.diagram_entities ?? {}"
        @shared="load"
      />
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

<style scoped src="./DiagramDetailView.css"></style>
