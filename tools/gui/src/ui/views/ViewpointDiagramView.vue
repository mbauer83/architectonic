<script setup lang="ts">
/**
 * Ad-hoc `diagram` execution representation: renders a
 * viewpoint's repository-context population through the same rendering engine as a real
 * diagram (fixed cross-layer ArchiMate notation), never persisted as a `.puml` artifact, no
 * `ViewpointApplication`. `node_color`/`edge_color`/`edge_emphasis` are highlight overlays
 * applied client-side onto the returned SVG — the same technique the ghost/hide
 * overlay uses on a real diagram, never baked into the rendered notation.
 */
import { computed, inject, nextTick, onMounted, ref, watch } from 'vue'
import { Cause, Effect } from 'effect'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { modelServiceKey } from '../keys'
import { useViewpointExecution } from '../composables/useViewpointExecution'
import { useViewpointParameterPrompt } from '../composables/useViewpointParameterPrompt'
import { executionTitleFor } from './ViewpointsManagementView.helpers'
import { useFittedPanZoom } from '../composables/useFittedPanZoom'
import { useFullscreen } from '../composables/useFullscreen'
import DiagramViewportOverlays from '../components/DiagramViewportOverlays.vue'
import ViewpointSaveAsDiagram from '../components/ViewpointSaveAsDiagram.vue'
import { diagramDetailRoute } from '../router/artifactRoutes'
import { useArrowPanning } from '../composables/useArrowPanning'
import { drawnMarksOf } from '../lib/diagramOverview'
import { useDiagramSvgSelection, type DiagramSvgSelectionDetail } from '../composables/useDiagramSvgSelection'
import { useSelectedConnectionWitnessChain } from '../composables/useSelectedConnectionWitnessChain'
import DiagramSplitLayout from '../components/DiagramSplitLayout.vue'
import DiagramEntitySidebar from '../components/DiagramEntitySidebar.vue'
import FullscreenDock from '../components/FullscreenDock.vue'
import ViewpointExecutionDiagnostics from '../components/ViewpointExecutionDiagnostics.vue'
import ViewpointExecutionError from '../components/ViewpointExecutionError.vue'
import ViewpointParameterPrompt from '../components/ViewpointParameterPrompt.vue'
import { computeExecutionDiagnostics, deriveLegend, deriveScaleGradients } from '../components/ViewpointExecutionDiagnostics.helpers'
import { presentationFromMapping } from '../../domain/viewpointPresentationSerialization'
import type { AdHocExecution } from '../lib/adHocExecution'
import type { ViewpointExecutionRequest } from '../../domain'
import type { SignalBanner } from '../../domain/schemas/viewpoints'
import SignalRenderBanner from '../components/SignalRenderBanner.vue'
import { sanitizeDiagramSvg } from '../lib/svgSanitize'
import { readApiErrorBody, readErrorMessage } from '../lib/errors'
import type { ErrorBody } from '../../domain/schemas/errors'
import { downloadStampedRender } from '../lib/stampedRenderExport'
import {
  anchorBadges, applyDiagramOverlay, centerAnchorsAfterFit,
  toDiagramConnectionStub, toDiagramContextEntityStub,
} from './ViewpointDiagramView.helpers'
import type { ViewpointDefinitionEnvelope } from '../../domain'

const props = defineProps<{ adHoc?: AdHocExecution }>()

const svc = inject(modelServiceKey)!
const route = useRoute()
const router = useRouter()
const slug = computed(() => route.params.slug as string)

const definitions = ref<readonly ViewpointDefinitionEnvelope[]>([])
const execution = useViewpointExecution(svc)
const svgMarkup = ref<string | null>(null)
const signalBanner = ref<SignalBanner | null>(null)
const diagramWarnings = ref<readonly string[]>([])
const diagramLoading = ref(false)
const diagramError = ref<string | null>(null)
//: The published envelope of a failed *diagram* call, kept beside its message for the same reason
//: the execution composable keeps one: `executionErrorDisplay` turns a code into prose a reader can
//: act on. Only the execution's envelope was passed on, so a query that ran fine and then produced
//: more than the renderer takes lost the backend's own "too large — use the table or narrow the
//: scope" and showed the bare fallback title instead.
const diagramTypedError = ref<ErrorBody | null>(null)
// A large scope legitimately takes tens of seconds; a silent placeholder reads as a
// hang. Ticking elapsed time is the honest signal that work is still happening.
const loadingElapsedSeconds = ref(0)
let loadingTicker: ReturnType<typeof setInterval> | null = null
const isExecuting = computed(() => execution.loading.value || diagramLoading.value)
watch(isExecuting, (active) => {
  if (loadingTicker) { clearInterval(loadingTicker); loadingTicker = null }
  loadingElapsedSeconds.value = 0
  if (active) loadingTicker = setInterval(() => { loadingElapsedSeconds.value += 1 }, 1000)
})
/** Whether *Save as diagram* is open over the picture. */
const savingAsDiagram = ref(false)
const entityAliases = ref<Readonly<Record<string, string>>>({})

const presentation = computed(() => {
  if (props.adHoc) return props.adHoc.presentation
  const envelope = definitions.value.find((d) => d.slug === slug.value)
  return envelope ? presentationFromMapping(envelope.presentation) : null
})
const diagnostics = computed(() => computeExecutionDiagnostics(execution.result.value, presentation.value, 'diagram'))
const legend = computed(() => deriveLegend(presentation.value, execution.projection.value?.rule_outcomes ?? []))
const scaleGradients = computed(() => deriveScaleGradients(presentation.value, execution.projection.value?.scale_legends ?? []))
const svgHtml = computed(() => (svgMarkup.value ? sanitizeDiagramSvg(svgMarkup.value) : null))

// ── Pan/zoom + click-to-select (same composables `DiagramDetailView.vue` uses for a
// persisted diagram) — this rendering is ephemeral, but the viewport/interactivity needs
// are identical, so nothing type-specific is duplicated here. ──────────────────────────
const detail = computed<DiagramSvgSelectionDetail>(() => ({ diagram_type: 'archimate-layered' }))
const aliasById = computed(() => new Map(Object.entries(entityAliases.value)))
const diagramEntities = computed(() =>
  execution.result.value?.entities.map((e) => toDiagramContextEntityStub(e, aliasById.value)) ?? [])
const diagramConnections = computed(() => {
  const result = execution.result.value
  if (!result) return []
  const nameById = new Map(result.entities.map((e) => [e.id, e.name]))
  return result.connections.map((c) => toDiagramConnectionStub(c, nameById, aliasById.value))
})
const noDrilldown = ref({})
const diagramIdRef = ref('')

const rerun = () => void load()

const selection = useDiagramSvgSelection({
  svc, router, svgHtml, detail, diagramEntities, diagramConnections,
  drilldownByEntityId: noDrilldown, diagramId: diagramIdRef, reload: rerun,
})
const { svgContainer } = selection

const { display: witnessChainDisplay } = useSelectedConnectionWitnessChain(svc, selection.selectedConnection)

const containerRef = ref<HTMLElement | null>(null)
const panZoom = useFittedPanZoom(containerRef, svgContainer)
const fullscreen = useFullscreen(containerRef)
useArrowPanning(containerRef, panZoom.panBy)
/** Every element drawn, named, for the overview to mark the selection and the names to be written (04·1). */
const drawn = computed(() => drawnMarksOf(selection.nodeElements.value,
  (id) => diagramEntities.value.find((entity) => entity.artifact_id === id)?.name,
  new Set(selection.selectedIds.value)))
// Entering or leaving fullscreen is a framing request: re-fit even when the view has been
// transformed, since the whole point of the gesture is to see the diagram against the new space.
watch(fullscreen.isFullscreen, () => { void panZoom.fitDiagramToViewport() })

watch(svgHtml, (svg) => { if (svg) void panZoom.fitDiagramToViewport() })

const anchorLegend = computed(() =>
  anchorBadges(execution.result.value?.anchor_ids ?? [], execution.result.value?.entities ?? []))

const applyOverlay = (): readonly Element[] => {
  const svgEl = svgContainer.value?.querySelector('svg')
  const result = execution.result.value
  if (!svgEl || !result) return []
  return applyDiagramOverlay(
    svgEl, execution.projection.value?.items ?? [],
    diagramEntities.value, diagramConnections.value, result.anchor_ids,
  )
}

const panBy = (dx: number, dy: number) => { panZoom.tx.value += dx; panZoom.ty.value += dy }

const runExecution = async (resolved: ViewpointExecutionRequest) => {
  await execution.execute(resolved)
  diagramLoading.value = true
  diagramError.value = null
  diagramTypedError.value = null
  const exit = await Effect.runPromiseExit(svc.executeViewpointDiagram(resolved))
  diagramLoading.value = false
  if (exit._tag === 'Success') {
    svgMarkup.value = exit.value.svg
    diagramWarnings.value = exit.value.warnings
    entityAliases.value = exit.value.entity_aliases ?? {}
    signalBanner.value = exit.value.signal_banner ?? null
  } else {
    const reason = Cause.squash(exit.cause)
    diagramError.value = readErrorMessage(reason)
    diagramTypedError.value = readApiErrorBody(reason)
  }
  await nextTick()
  await centerAnchorsAfterFit(applyOverlay(), containerRef.value, panZoom.fitDiagramToViewport, panBy)
}
const prompt = useViewpointParameterPrompt(runExecution, definitions)

const exportStampedRender = async () => {
  const svgEl = svgContainer.value?.querySelector('svg')
  if (!svgEl || !slug.value) return
  const error = await downloadStampedRender(slug.value, svgEl.outerHTML)
  if (error) diagramError.value = error
}

const load = async () => {
  definitions.value = await Effect.runPromise(svc.listViewpointDefinitions()).catch(() => [])
  if (props.adHoc) { await runExecution(props.adHoc.request); return }
  await prompt.run(slug.value)
}

onMounted(() => { if (props.adHoc || slug.value) void load() })
</script>

<template>
  <div class="page">
    <div class="hdr">
      <h1 class="pg-title">
        {{ executionTitleFor(slug, definitions) }} <span class="count">— diagram</span>
      </h1>
      <div class="hdr-actions">
        <button
          v-if="svgHtml && execution.result.value"
          type="button"
          class="view-as-link"
          data-testid="viewpoint-save-as-diagram"
          @click="savingAsDiagram = true"
        >
          Save as diagram…
        </button>
        <RouterLink
          v-if="!adHoc && slug"
          :to="{ path: '/viewpoints/query', query: { slug } }"
          class="view-as-link"
          title="Re-present this saved viewpoint with a different presentation, without changing it"
        >
          View as… (unsaved)
        </RouterLink>
        <RouterLink
          to="/viewpoints"
          class="back-link"
        >
          ← Viewpoints
        </RouterLink>
      </div>
    </div>

    <ViewpointSaveAsDiagram
      v-if="savingAsDiagram && execution.result.value"
      :name="executionTitleFor(slug, definitions)"
      :execution="execution.result.value"
      @saved="router.push(diagramDetailRoute($event))"
      @cancel="savingAsDiagram = false"
    />

    <ViewpointExecutionDiagnostics
      v-if="!prompt.visible.value && !execution.errorMessage.value && !diagramError"
      :diagnostics="diagnostics"
      :legend="legend"
      :scale-gradients="scaleGradients"
      :query-summary="execution.result.value?.query_summary ?? ''"
      @rerun="rerun"
    />

    <SignalRenderBanner
      v-if="signalBanner"
      :banner="signalBanner"
      @export="exportStampedRender"
    />

    <div
      v-if="anchorLegend.length && !prompt.visible.value"
      class="anchor-legend"
    >
      <span
        v-for="badge in anchorLegend"
        :key="badge.id"
        class="anchor-badge"
      >◎ anchor: {{ badge.name }}</span>
    </div>

    <div
      v-for="warning in diagramWarnings"
      :key="warning"
      class="diagram-warning"
    >
      {{ warning }}
    </div>

    <ViewpointParameterPrompt
      v-if="prompt.visible.value"
      :parameters="prompt.parameters.value"
      @submit="prompt.submit"
      @cancel="prompt.cancel"
    />

    <div
      v-if="isExecuting"
      class="state-msg viewpoint-loading"
      role="status"
    >
      <span
        class="viewpoint-loading__spinner"
        aria-hidden="true"
      />
      <span>
        Executing the viewpoint query and rendering the diagram…
        <template v-if="loadingElapsedSeconds >= 3"> {{ loadingElapsedSeconds }}s —
          large scopes with derived traversals can take a while.</template>
      </span>
    </div>
    <ViewpointExecutionError
      v-else-if="execution.errorMessage.value || diagramError"
      :typed-error="execution.typedError.value ?? diagramTypedError"
      :fallback-message="execution.errorMessage.value || diagramError || 'Execution failed'"
      @retry="rerun"
    />
    <DiagramSplitLayout v-else-if="svgHtml">
      <template #canvas>
        <div
          ref="containerRef"
          class="img-container viewport-host"
          tabindex="0"
          :aria-label="`Diagram ${executionTitleFor(slug, definitions)}: arrows pan, + and − zoom, 0 fits`"
          @mousedown="panZoom.onMouseDown"
        >
          <div
            class="pan-canvas"
            :style="panZoom.canvasStyle.value"
          >
            <div
              ref="svgContainer"
              class="svg-wrap"
              v-html="svgHtml"
            />
          </div>
          <DiagramViewportOverlays
            :window="panZoom"
            :picture="svgContainer"
            :marks="drawn.filter((mark) => mark.selected)"
            :boxes="drawn"
            :is-fullscreen="fullscreen.isFullscreen.value"
            :can-fullscreen="fullscreen.isSupported"
            hint="Scroll to zoom · Drag or arrows to pan · Click entity to inspect · 0 fits"
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
            :entity-query="selection.entityQuery"
            :edge-label-input="selection.edgeLabelInput.value"
            :edge-label-error="selection.edgeLabelMutation.errorMessage.value"
            :witness-chain="witnessChainDisplay"
            @select-entity="selection.selectEntity($event)"
            @find="selection.selectEntity($event)"
            @clear-connection="selection.clearConnection()"
            @clear-sub-part="selection.clearSubPart()"
            @update:edge-label-input="selection.edgeLabelInput.value = $event"
            @save-edge-label="selection.saveEdgeLabel()"
            @entity-edited="selection.entityEdited()"
          />
        </FullscreenDock>
      </template>
    </DiagramSplitLayout>
    <div
      v-else
      class="state-msg"
    >
      Nothing to render.
    </div>
  </div>
</template>

<style scoped src="./ViewpointDiagramView.css"></style>
