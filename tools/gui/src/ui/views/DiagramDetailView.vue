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
  editableMetadataByEntityType, isADifferentDiagram, matrixHtmlOf, offersAutomaticLayout, viewportHint,
} from './DiagramDetailView.helpers'
import { membershipOf } from '../../domain/layout/diagramMembership'
import DrilldownMenu from '../components/DrilldownMenu.vue'
import DiagramReadingPanel from '../components/DiagramReadingPanel.vue'
import { useDiagramReadingLens } from '../composables/useDiagramReadingLens'
import { useFittedPanZoom } from '../composables/useFittedPanZoom'
import { useFullscreen } from '../composables/useFullscreen'
import DiagramViewportOverlays from '../components/DiagramViewportOverlays.vue'
import { useDiagramSvgSelection } from '../composables/useDiagramSvgSelection'
import DiagramSplitLayout from '../components/DiagramSplitLayout.vue'
import DiagramDetailHeader from '../components/DiagramDetailHeader.vue'
import DiagramC4Navigation from '../components/DiagramC4Navigation.vue'
import CanvasContentEditor from '../components/CanvasContentEditor.vue'
import DiagramPageSidebar from '../components/DiagramPageSidebar.vue'
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
import { useDiagramPageReader } from '../composables/useDiagramPageReader'
import { useDiagramDrafts } from '../composables/useDiagramDrafts'
import PumlSourceToggle from '../components/PumlSourceToggle.vue'
import DiagramMetaLine from '../components/DiagramMetaLine.vue'

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
    .sort((a, b) => a.domain.localeCompare(b.domain) || a.artifact_type.localeCompare(b.artifact_type)
      || a.name.localeCompare(b.name))
)
const diagramConnections = computed(() => contextQuery.data.value?.connections ?? [])

const matrixHtml = computed(() =>
  matrixHtmlOf(detail.value?.diagram_type, detail.value?.type_extras, renderMatrixMarkdown))
const editPath = computed(() =>
  editRouteFor(detail.value?.diagram_type, diagramId.value, matrixEditRoute, diagramEditRoute))
const isGlobalDiagram = computed(() => detail.value?.is_global ?? false)

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
// `ref="svgContainer"` needs a top-level binding by that name: the composable's ref, aliased, not copied.
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
const edit = useDiagramEditMode(
  svc, diagramId, {
    canvas: editCanvas, bar: editBar, membership: () => membershipOf(detail.value), lens: () => lens.value,
    context: () => contextQuery.data.value,
    view: panZoom, host: containerRef, large: () => panZoom.large.value,
  }, load, toast,
)
const editing = computed(() => edit.active.value)
const drafts = useDiagramDrafts({
  context: contextQuery.data, editing: edit.editing, nodeElements: selection.nodeElements,
})
watch(editing, () => { void panZoom.fitDiagramToViewport() })
watch(() => edit.session.geometry.value, () => { if (editing.value) void panZoom.fitDiagramToViewport() })

// The diagram reader (B97): in view mode only, on the picture's own selection and window.
const reader = useDiagramPageReader({
  svc, route, router, context: contextQuery.data, selection, panZoom, host: containerRef, toast,
  viewing: computed(() => !editing.value && svgHtml.value !== null),
})

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
      :lays-out-automatically="offersAutomaticLayout(detail)"
      :editing="editing"
      @sync="syncPanel?.requestSync()"
      @delete="deletePanel?.requestDelete()"
      @edit="edit.enter()"
      @done="edit.done()"
      @laid-out="load"
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
      <DiagramMetaLine
        :detail="detail"
        :editing="editing"
      />

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

      <DiagramSplitLayout :sidebar-collapsed="editing && !edit.panel.open.value">
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
            v-bind="reader.hostAttributes.value"
            @keydown="reader.onKeydown"
            @mousedown="editing ? edit.panPress($event, panZoom.onMouseDown) : panZoom.onMouseDown($event)"
            @pointerdown="editing && !edit.spaceHeld.value && editCanvas?.sweepFrom($event)"
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
                <CanvasContentEditor
                  v-if="contextQuery.data.value"
                  :editing="edit.editing"
                  :context="contextQuery.data.value"
                  :selection="editCanvas?.selected"
                  :line="editCanvas?.selectedLine"
                  :selected-shapes="editCanvas?.selection"
                  :focused="editCanvas?.announced"
                  @select="editCanvas?.select($event)"
                >
                  <LayoutLabCanvas
                    ref="editCanvas"
                    :session="edit.session"
                    :show-breaches="edit.checking.value"
                    :surround="edit.surround.value"
                    :drafts="drafts.inEdit.value"
                    :pending-lines="drafts.pendingLines.value"
                    :outlined="edit.outlined.value"
                  />
                </CanvasContentEditor>
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
            <DiagramViewportOverlays
              :window="panZoom"
              :picture="svgContainer"
              :marks="editing ? edit.marks.value : reader.marks.value"
              :reading="reader.marks.value"
              :boxes="reader.boxes.value"
              :edit="!editing && editsOnCanvas(detail) ? edit.enter : null"
              :is-fullscreen="fullscreen.isFullscreen.value"
              :can-fullscreen="fullscreen.isSupported"
              :hint="viewportHint(editing)"
              @toggle-fullscreen="fullscreen.toggle"
            />
          </div>
        </template>

        <template #sidebar>
          <DiagramPageSidebar
            :context="contextQuery.data.value"
            :entities="diagramEntities"
            :editable-metadata-by-type="editableMetadataByType"
            :selection="selection"
            :reader="reader"
            :edit="edit"
            :editing="editing"
            :fullscreen-host="containerRef"
            :is-fullscreen="fullscreen.isFullscreen.value"
          />
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

      <PumlSourceToggle
        v-if="detail.puml_source"
        :source="detail.puml_source"
      />
    </template>
  </div>
</template>

<style scoped src="./DiagramDetailView.css"></style>
