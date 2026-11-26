<script setup lang="ts">
/**
 * A diagram drawn by the diagram canvas (`DiagramCanvas`), read only, with its reader's marks over
 * it: a candidate against its base, and whatever else the reader marks (a stress analysis marks what
 * its focus hits). A press on an element answers `pick` with its entity id, which is how a stress
 * analysis makes a tick on the picture.
 *
 * It can take the whole screen (`useFullscreen`, as the diagram page does). What a reader works with beside it
 * is docked over it by the reader (`FullscreenDock`), into the element it exposes as `frameEl`; the marks and
 * whatever is selected are the reader's, so entering or leaving changes neither.
 */
import { computed, inject, ref, shallowRef, watch } from 'vue'
import { Effect } from 'effect'
import type { DiagramContext } from '../../../domain'
import type { LayoutGeometry } from '../../../domain/schemas/diagramLayoutGeometry'
import type { Marks } from '../../../domain/candidates/elementMarks'
import { modelServiceKey } from '../../keys'
import { useArrangementSession } from '../../composables/useArrangementSession'
import { useDrawnEntities } from '../../composables/useDrawnEntities'
import { useFittedPanZoom } from '../../composables/useFittedPanZoom'
import { useFullscreen } from '../../composables/useFullscreen'
import DiagramCanvas from '../canvas/DiagramCanvas.vue'
import DiagramViewportOverlays from '../DiagramViewportOverlays.vue'
import ElementMarksLayer from './ElementMarksLayer.vue'

const props = defineProps<{
  diagramId: string
  drawing: LayoutGeometry | null
  /**
   * The picture shown is the one served, standing in while the candidate is drawn as it composes
   * (`useComposedDrawing`): it is said to be loading, and stepped back, until the composed one arrives.
   */
  composing?: boolean
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
const session = useArrangementSession(() => Effect.succeed([]))
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
const fullscreen = useFullscreen(containerRef)
const panZoom = useFittedPanZoom(containerRef, svgContainer, fullscreen.isFullscreen)
watch(() => session.geometry.value, () => { void panZoom.fitDiagramToViewport() })
/** A tag is the same size on screen however far the picture is zoomed: one drawing unit is `scale` pixels. */
const tagSize = computed(() => 12 / Math.max(panZoom.scale.value, 0.05))

defineExpose({
  /** The element the browser makes fullscreen, and so the host a docked panel teleports into. */
  frameEl: containerRef,
  isFullscreen: fullscreen.isFullscreen,
})
</script>

<template>
  <div
    ref="containerRef"
    class="img-container viewport-host workspace-canvas"
    data-testid="workspace-canvas"
    @mousedown="panZoom.onMouseDown"
  >
    <div
      class="pan-canvas"
      :style="panZoom.canvasStyle.value"
    >
      <div
        v-if="drawing"
        ref="svgContainer"
        class="svg-wrap"
        :class="{ composing }"
      >
        <DiagramCanvas
          :session="session"
          readonly
          @pick="pick"
        >
          <ElementMarksLayer
            :session="session"
            :entity-of="entityOf"
            :marks="marks"
            :dimmed="dimmed"
            :tag-size="tagSize"
          />
        </DiagramCanvas>
      </div>
      <p
        v-else
        class="no-img"
      >
        {{ emptyText ?? 'No diagram to draw.' }}
      </p>
    </div>
    <p
      v-if="drawing && composing"
      class="composing-note"
      role="status"
      data-testid="canvas-composing"
    >
      Loading the candidate's changes onto the picture…
    </p>
    <DiagramViewportOverlays
      :window="panZoom"
      :picture="svgContainer"
      :hint="hint"
      :is-fullscreen="fullscreen.isFullscreen.value"
      :can-fullscreen="fullscreen.isSupported"
      @toggle-fullscreen="fullscreen.toggle"
    />
  </div>
</template>

<style scoped>
.workspace-canvas {
  position: relative; overflow: hidden; background: var(--paper);
  border: 1px solid var(--border); border-radius: 8px;
  height: clamp(380px, calc(100vh - 300px), 900px); cursor: grab; user-select: none;
}
/* Fullscreen overrides the clamped height, and the browser paints black behind what the element does not cover. */
.workspace-canvas:fullscreen { width: 100vw; height: 100vh; max-height: none; border: none; border-radius: 0; }
.svg-wrap :deep(svg) { display: block; max-width: none; }
.svg-wrap.composing { opacity: 0.35; }
.composing-note {
  position: absolute; top: 12px; left: 12px; right: 12px; margin: 0; padding: 6px 10px; width: fit-content;
  max-width: calc(100% - 24px); background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-2); font-size: 12.5px;
}
.no-img { padding: 60px 40px; text-align: center; color: var(--on-paper); font-size: 13px; }
</style>
