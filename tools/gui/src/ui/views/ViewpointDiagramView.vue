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
import { Effect } from 'effect'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { modelServiceKey } from '../keys'
import { useViewpointExecution } from '../composables/useViewpointExecution'
import { useViewpointParameterPrompt } from '../composables/useViewpointParameterPrompt'
import { executionTitleFor } from './ViewpointsManagementView.helpers'
import { useFittedPanZoom } from '../composables/useFittedPanZoom'
import { useFullscreen } from '../composables/useFullscreen'
import DiagramViewportControls from '../components/DiagramViewportControls.vue'
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
  const exit = await Effect.runPromiseExit(svc.executeViewpointDiagram(resolved))
  diagramLoading.value = false
  if (exit._tag === 'Success') {
    svgMarkup.value = exit.value.svg
    diagramWarnings.value = exit.value.warnings
    entityAliases.value = exit.value.entity_aliases ?? {}
    signalBanner.value = exit.value.signal_banner ?? null
  } else {
    diagramError.value = String(exit.cause)
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
      :typed-error="execution.typedError.value"
      :fallback-message="execution.errorMessage.value || diagramError || 'Execution failed'"
      @retry="rerun"
    />
    <DiagramSplitLayout v-else-if="svgHtml">
      <template #canvas>
        <div
          ref="containerRef"
          class="img-container viewport-host"
          @mousedown="panZoom.onMouseDown"
          @dblclick="panZoom.resetView"
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
          <DiagramViewportControls
            :is-transformed="panZoom.isTransformed.value"
            :is-fullscreen="fullscreen.isFullscreen.value"
            :can-fullscreen="fullscreen.isSupported"
            hint="Scroll to zoom · Drag to pan · Click entity to inspect · Double-click to reset"
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
            :entity-query="selection.entityQuery"
            :edge-label-input="selection.edgeLabelInput.value"
            :edge-label-error="selection.edgeLabelMutation.errorMessage.value"
            :witness-chain="witnessChainDisplay"
            @select-entity="selection.selectEntity($event)"
            @clear-connection="selection.clearConnection()"
            @clear-sub-part="selection.clearSubPart()"
            @update:edge-label-input="selection.edgeLabelInput.value = $event"
            @save-edge-label="selection.saveEdgeLabel()"
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

<style scoped>
.viewpoint-loading { display: flex; align-items: center; gap: 10px; }
.viewpoint-loading__spinner {
  width: 16px; height: 16px; flex: none; border-radius: 50%;
  border: 2px solid #d1d5db; border-top-color: #4b5563;
  animation: viewpoint-loading-spin 0.8s linear infinite;
}
@keyframes viewpoint-loading-spin { to { transform: rotate(360deg); } }

.page { max-width: 100%; padding: 24px 16px; }
.hdr { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.pg-title { font-size: 20px; font-weight: 600; margin: 0; }
.count { color: #6b7280; font-weight: 400; font-size: 14px; }
.hdr-actions { display: flex; align-items: center; gap: 14px; }
.back-link { font-size: 13px; color: #6b7280; text-decoration: none; }
.back-link:hover { color: #374151; }
.view-as-link { font-size: 13px; color: #4338ca; text-decoration: none; border: 1px solid #c7d2fe; border-radius: 6px; padding: 4px 10px; }
.view-as-link:hover { background: #eef2ff; }
.state-msg { color: #9ca3af; font-size: 14px; padding: 24px 0; }
.state-msg--error { color: #dc2626; }
.diagram-warning { color: #92400e; background: #fef3c7; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-bottom: 6px; }
.anchor-legend { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.anchor-badge { color: #6d28d9; background: #f5f3ff; border: 1px dashed #8b5cf6; border-radius: 4px; padding: 2px 8px; font-size: 12px; }

.img-container {
  position: relative; overflow: hidden; background: #f8fafc;
  border: 1px solid #e5e7eb; border-radius: 8px;
  min-height: 400px; height: clamp(420px, 78vh, 980px);
  cursor: grab; user-select: none;
}
@media (max-width: 800px) { .img-container { height: clamp(360px, 68vh, 820px); } }
.img-container:active { cursor: grabbing; }
/* Fullscreen overrides the clamped height, and the browser paints black behind
   anything the element does not cover. */
.img-container:fullscreen {
  width: 100vw; height: 100vh; max-height: none;
  border: none; border-radius: 0; background: #f8fafc;
}
.svg-wrap { display: inline-block; padding: 12px; }
.svg-wrap :deep(svg) { display: block; max-width: none; }
.svg-wrap :deep([data-entity-id]) { cursor: pointer; }
/* Group-scoped: the viewer sets `.svg-hovered` on every element the artifact maps to, because
   `:hover` can only reach the one text run under the pointer. See `useDiagramSvgSelection`. */
.svg-wrap :deep(.svg-hovered) > :not(title) { opacity: 0.85; }
.svg-wrap :deep(.svg-hovered) polygon,
.svg-wrap :deep(.svg-hovered) rect,
.svg-wrap :deep(.svg-hovered) polyline,
.svg-wrap :deep(.svg-hovered) ellipse { stroke: #2563eb !important; stroke-width: 2 !important; }
.svg-wrap :deep(a.svg-hovered) text { fill: #2563eb !important; }
.svg-wrap :deep(rect.svg-hovered),
.svg-wrap :deep(polygon.svg-hovered) { stroke: #2563eb !important; stroke-width: 2 !important; }
.svg-wrap :deep(.svg-selected) polygon,
.svg-wrap :deep(.svg-selected) rect,
.svg-wrap :deep(.svg-selected) polyline,
.svg-wrap :deep(.svg-selected) ellipse { stroke: #2563eb !important; stroke-width: 2.5 !important; }
.svg-wrap :deep([data-conn-id]) { cursor: pointer; }
.svg-wrap :deep([data-conn-id]:hover) path,
.svg-wrap :deep([data-conn-id]:hover) polygon,
.svg-wrap :deep([data-conn-id]:hover) line,
.svg-wrap :deep([data-conn-id]:hover) polyline { stroke: #2563eb !important; stroke-width: 2 !important; }
.svg-wrap :deep(.svg-conn-selected) path,
.svg-wrap :deep(.svg-conn-selected) polygon,
.svg-wrap :deep(.svg-conn-selected) line,
.svg-wrap :deep(.svg-conn-selected) polyline { stroke: #2563eb !important; stroke-width: 2.5 !important; }
</style>
