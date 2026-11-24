<script setup lang="ts">
/**
 * A diagram drawn by the diagram canvas (`LayoutLabCanvas`), read only, with its reader's marks over
 * it: a candidate against its base, and whatever else the reader marks (a stress analysis marks what
 * its focus hits). A press on an element answers `pick` with its entity id, which is how a stress
 * analysis makes a tick on the picture.
 */
import { computed, inject, ref, shallowRef, watch } from 'vue'
import { Effect } from 'effect'
import type { DiagramContext } from '../../../domain'
import type { LayoutGeometry } from '../../../domain/schemas/diagramLayoutGeometry'
import type { Marks } from '../../../domain/candidates/canvasMarks'
import { modelServiceKey } from '../../keys'
import { useArrangementSession } from '../../composables/useArrangementSession'
import { useDrawnEntities } from '../../composables/useDrawnEntities'
import { useFittedPanZoom } from '../../composables/useFittedPanZoom'
import LayoutLabCanvas from '../layoutLab/LayoutLabCanvas.vue'
import DiagramViewportControls from '../DiagramViewportControls.vue'
import CanvasMarksLayer from './CanvasMarksLayer.vue'

const props = defineProps<{
  diagramId: string
  drawing: LayoutGeometry | null
  marks: Marks
  /** Elements outside what is being looked at, by stable id: drawn stepped back. */
  dimmed?: ReadonlySet<string>
  hint: string
  /** What is said where there is no drawing. */
  emptyText?: string
}>()
const emit = defineEmits<{ pick: [stableId: string] }>()
const svc = inject(modelServiceKey)!

// Read only: nothing is moved, so no shape is ever drawn anew and no picture is taken over.
const session = useArrangementSession(() => Effect.succeed([]), (_, automatic) => automatic)
watch(() => props.drawing, (drawing) => {
  if (drawing) session.open(drawing)
  else session.close()
}, { immediate: true })
const context = shallowRef<DiagramContext | null>(null)
watch(() => props.diagramId, async (id) => {
  context.value = id ? await Effect.runPromise(svc.getDiagramContext(id)).catch(() => null) : null
}, { immediate: true })
const entityOf = useDrawnEntities(() => context.value, () => props.drawing)

const pick = (alias: string) => {
  const stableId = entityOf.value.get(alias)
  if (stableId) emit('pick', stableId)
}

const containerRef = ref<HTMLElement | null>(null)
const svgContainer = ref<HTMLElement | null>(null)
const panZoom = useFittedPanZoom(containerRef, svgContainer)
watch(() => session.geometry.value, () => { void panZoom.fitDiagramToViewport() })
/** A tag is the same size on screen however far the picture is zoomed: one drawing unit is `scale` pixels. */
const tagSize = computed(() => 12 / Math.max(panZoom.scale.value, 0.05))
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
          <CanvasMarksLayer
            :session="session"
            :entity-of="entityOf"
            :marks="marks"
            :dimmed="dimmed"
            :tag-size="tagSize"
          />
        </LayoutLabCanvas>
      </div>
      <p
        v-else
        class="no-img"
      >
        {{ emptyText ?? 'No diagram to draw.' }}
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
  position: relative; overflow: hidden; background: var(--paper);
  border: 1px solid var(--border); border-radius: 8px;
  height: clamp(380px, calc(100vh - 300px), 900px); cursor: grab; user-select: none;
}
.svg-wrap :deep(svg) { display: block; max-width: none; }
.no-img { padding: 60px 40px; text-align: center; color: var(--on-paper); font-size: 13px; }
</style>
