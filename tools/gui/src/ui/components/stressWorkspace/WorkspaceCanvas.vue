<script setup lang="ts">
/**
 * The workspace's picture: the scope diagram drawn by the diagram canvas (`LayoutLabCanvas`), read
 * only, with the workspace's marks over it — what the focus hits, and a candidate against its base.
 * A press on an element answers `pick` with its entity id, which is how a tick is made on the picture.
 */
import { computed, inject, ref, watch } from 'vue'
import { Effect } from 'effect'
import type { LayoutGeometry } from '../../../domain/schemas/diagramLayoutGeometry'
import type { Extent } from '../../../domain/layout/geometry'
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import { stableEntityId } from '../../../domain/artifactId'
import type { Marks } from '../../../domain/stressAnalysis/workspaceMarks'
import { modelServiceKey } from '../../keys'
import { occurrenceItems } from '../../lib/archimateOccurrences'
import { useArrangementSession } from '../../composables/useArrangementSession'
import { useFittedPanZoom } from '../../composables/useFittedPanZoom'
import LayoutLabCanvas from '../layoutLab/LayoutLabCanvas.vue'
import DiagramViewportControls from '../DiagramViewportControls.vue'

const props = defineProps<{
  diagramId: string
  drawing: LayoutGeometry | null
  marks: Marks
  /** Elements outside what is being looked at, by stable id: drawn stepped back. */
  dimmed?: ReadonlySet<string>
  hint: string
}>()
const emit = defineEmits<{ pick: [stableId: string] }>()
const svc = inject(modelServiceKey)!

// Read only: nothing is moved, so no shape is ever drawn anew and no picture is taken over.
const session = useArrangementSession(() => Effect.succeed([]), (_, automatic) => automatic)
watch(() => props.drawing, (drawing) => { if (drawing) session.open(drawing); else session.close() }, { immediate: true })

/** A further occurrence of an entity, by occurrence id, as the entity it draws. */
const occurrences = ref<ReadonlyMap<string, string>>(new Map())
watch(() => props.diagramId, async (id) => {
  if (!id) return
  const context = await Effect.runPromise(svc.getDiagramContext(id)).catch(() => null)
  const items = occurrenceItems(context?.diagram.diagram_entities ?? {})
  occurrences.value = new Map(items.map((item) => [item.id, stableEntityId(item.backing_entity_id)]))
}, { immediate: true })

/** Each drawn element's entity, by alias. */
const entityOf = computed(() => new Map((props.drawing?.elements ?? []).flatMap((element) => {
  const key = element.key
  return key ? [[element.alias, occurrences.value.get(key) ?? stableEntityId(key)] as const] : []
})))

const drawn = (filter: (stableId: string) => boolean): { alias: string; extent: Extent; stableId: string }[] => {
  const where = session.placement.value
  return [...entityOf.value].flatMap(([alias, stableId]) => {
    const extent = where?.elements.get(alias)
    return extent && filter(stableId) ? [{ alias, extent, stableId }] : []
  })
}
const marked = computed(() => drawn((id) => props.marks.has(id))
  .map((one) => ({ ...one, mark: props.marks.get(one.stableId)! })))
const stepped = computed(() => drawn((id) => props.dimmed?.has(id) ?? false))

const pick = (alias: string) => {
  const stableId = entityOf.value.get(alias)
  if (stableId) emit('pick', stableId)
}

const containerRef = ref<HTMLElement | null>(null)
const svgContainer = ref<HTMLElement | null>(null)
const panZoom = useFittedPanZoom(containerRef, svgContainer)
watch(() => session.geometry.value, () => { void panZoom.fitDiagramToViewport() })
/** A tag is the same size on screen however far the picture is zoomed: one drawing unit is `scale` pixels. */
const TAG_PIXELS = 12
const tagSize = computed(() => TAG_PIXELS / Math.max(panZoom.scale.value, 0.05))
</script>

<template>
  <div
    ref="containerRef"
    class="img-container viewport-host workspace-canvas"
    data-testid="workspace-canvas"
    @mousedown="panZoom.onMouseDown"
    @dblclick="panZoom.resetView()"
  >
    <div
      class="pan-canvas"
      :style="panZoom.canvasStyle.value"
    >
      <div
        v-if="drawing"
        ref="svgContainer"
        class="svg-wrap"
      >
        <LayoutLabCanvas
          :session="session"
          readonly
          @pick="pick"
        >
          <rect
            v-for="one in stepped"
            :key="`dim:${one.alias}`"
            class="ws-dim"
            :x="one.extent.left - 2"
            :y="one.extent.top - 2"
            :width="widthOf(one.extent) + 4"
            :height="heightOf(one.extent) + 4"
          />
          <g
            v-for="one in marked"
            :key="`mark:${one.alias}`"
            :class="`ws-mark ws-mark--${one.mark.kind}`"
            :data-marked="one.stableId"
          >
            <title>{{ one.mark.title }}</title>
            <rect
              class="ws-mark-frame"
              :x="one.extent.left - 3"
              :y="one.extent.top - 3"
              :width="widthOf(one.extent) + 6"
              :height="heightOf(one.extent) + 6"
              rx="4"
            />
            <text
              class="ws-mark-tag"
              :x="one.extent.right + 2"
              :y="one.extent.top - 4"
              :font-size="tagSize"
            >
              {{ one.mark.tag }}
            </text>
          </g>
        </LayoutLabCanvas>
      </div>
      <p
        v-else
        class="no-img"
      >
        No diagram to draw: this analysis has no scope diagram.
      </p>
    </div>
    <DiagramViewportControls
      :is-transformed="panZoom.isTransformed.value"
      :is-fullscreen="false"
      :can-fullscreen="false"
      :hint="hint"
      @reset="panZoom.resetView"
      @toggle-fullscreen="() => {}"
    />
  </div>
</template>

<style scoped>
.workspace-canvas {
  position: relative; overflow: hidden; background: var(--paper, #fff);
  border: 1px solid var(--border); border-radius: 8px;
  height: clamp(380px, calc(100vh - 300px), 900px); cursor: grab; user-select: none;
}
.svg-wrap :deep(svg) { display: block; max-width: none; }
.no-img { padding: 60px 40px; text-align: center; color: var(--muted); font-size: 13px; }
.ws-dim { fill: #fff; fill-opacity: 0.72; pointer-events: none; }
.ws-mark { pointer-events: none; }
.ws-mark-frame { fill: none; stroke-width: 2.5px; vector-effect: non-scaling-stroke; }
.ws-mark-tag { font-family: system-ui, sans-serif; font-weight: 700; paint-order: stroke; stroke: #fff; stroke-width: 0.3em; stroke-linejoin: round; }
.ws-mark--hit .ws-mark-frame { stroke: #1e293b; }
.ws-mark--hit .ws-mark-tag { fill: #1e293b; }
.ws-mark--added .ws-mark-frame { stroke: #15803d; }
.ws-mark--added .ws-mark-tag { fill: #15803d; }
.ws-mark--edited .ws-mark-frame { stroke: #b45309; }
.ws-mark--edited .ws-mark-tag { fill: #b45309; }
.ws-mark--removed .ws-mark-frame { stroke: #b91c1c; stroke-dasharray: 5 3; fill: #fff; fill-opacity: 0.6; }
.ws-mark--removed .ws-mark-tag { fill: #b91c1c; }
.ws-mark--framed .ws-mark-frame { stroke: var(--accent); stroke-width: 3px; }
</style>
