<script setup lang="ts">
/**
 * The overview over a diagram canvas (D13; owner Q20, F10), in view mode and in edit mode alike: a
 * still copy of the whole picture with the window drawn on it, and the selection and the reading
 * marked, so an element thousands of pixels away can be seen and reached. A press or a drag on it
 * moves the window there.
 *
 * It is HTML beside the picture, so nothing that exports the picture can carry it, and print hides it.
 * It shows only while the pointer is over the canvas or focus is inside it, fading in and out, and
 * not at all while the whole picture is in the window. Its shape follows the picture's
 * (`overviewShapeOf`).
 *
 * The copy is taken again a moment after the picture stops changing — a re-render, an arrangement
 * dropped — not on every frame of a drag, which would cost the drag its frame budget.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { Extent } from '../../domain/layout/geometry'
import { heightOf, widthOf } from '../../domain/layout/geometry'
import type { ReadingView } from '../../domain/diagramReading'
import { useElementSize } from '../composables/useElementSize'
import {
  drawingCopyOf, markExtent, overviewShapeOf, pictureBoxOf, windowShowsAll, type OverviewMark,
} from '../lib/diagramOverview'

const props = defineProps<{
  /** The element the picture's `<svg>` is mounted in. */
  picture: HTMLElement | null
  /** The part of the picture a window of the given size shows; and showing a part of it. */
  windowExtent: (width: number, height: number) => Extent
  scale: number
  showView: (view: ReadingView) => void
  marks: readonly OverviewMark[]
}>()

/** How long the picture must hold still before the copy is taken again. */
const SETTLE_MS = 250
/** The least size of a mark, in overview pixels: an element that would be a speck is still seen. */
const MARK_PIXELS = 5

const root = ref<HTMLElement | null>(null)
const thumb = ref<SVGGElement | null>(null)
const canvas = useElementSize(() => root.value?.parentElement)
const box = ref<Extent | null>(null)

let observer: MutationObserver | null = null
let timer: ReturnType<typeof setTimeout> | undefined
const copy = () => {
  const svg = props.picture?.querySelector('svg')
  box.value = svg ? pictureBoxOf(svg) : null
  if (svg && thumb.value) thumb.value.replaceChildren(...drawingCopyOf(svg))
}
const later = (records: MutationRecord[]) => {
  // Zooming resizes the `<svg>` itself; only a change to what it draws is a new picture.
  if (records.every((record) => record.target instanceof SVGSVGElement && record.type === 'attributes')) return
  clearTimeout(timer)
  timer = setTimeout(copy, SETTLE_MS)
}
watch([() => props.picture, thumb], ([picture]) => {
  observer?.disconnect()
  if (!picture) { box.value = null; return }
  observer = new MutationObserver(later)
  observer.observe(picture, { subtree: true, childList: true, attributes: true, characterData: true })
  copy()
}, { immediate: true, flush: 'post' })
onBeforeUnmount(() => { observer?.disconnect(); clearTimeout(timer) })

const shown = computed(() => (canvas.width.value > 0 ? props.windowExtent(canvas.width.value, canvas.height.value)
  : null))
const shape = computed(() => (box.value ? overviewShapeOf(box.value, canvas.width.value) : null))
const needed = computed(() => Boolean(box.value && shown.value && !windowShowsAll(shown.value, box.value)))
const viewBox = computed(() => {
  const at = box.value
  return at ? `${at.left} ${at.top} ${widthOf(at)} ${heightOf(at)}` : '0 0 1 1'
})
const least = computed(() => (box.value && shape.value ? MARK_PIXELS * widthOf(box.value) / shape.value.width : 0))
const drawnMarks = computed(() => props.marks.map((mark) => ({ ...mark, at: markExtent(mark.extent, least.value) })))

const svg = ref<SVGSVGElement | null>(null)
let dragging = false
const moveTo = (event: PointerEvent) => {
  const matrix = svg.value?.getScreenCTM()
  if (!matrix || !svg.value) return
  const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
  props.showView({ x: point.x, y: point.y, percent: props.scale * 100 })
}
const press = (event: PointerEvent) => {
  if (event.button !== 0) return
  dragging = true
  svg.value?.setPointerCapture?.(event.pointerId)
  moveTo(event)
}
</script>

<template>
  <div
    v-show="needed"
    ref="root"
    class="diagram-overview"
    :class="shape?.kind"
    :style="shape ? { width: `${shape.width}px`, height: `${shape.height}px` } : undefined"
    aria-hidden="true"
    data-testid="diagram-overview"
    @mousedown.stop
    @pointerdown.stop
    @dblclick.stop
  >
    <svg
      ref="svg"
      :viewBox="viewBox"
      @pointerdown="press"
      @pointermove="dragging && moveTo($event)"
      @pointerup="dragging = false"
      @pointercancel="dragging = false"
    >
      <rect
        class="ov-paper"
        :x="box?.left"
        :y="box?.top"
        :width="box ? widthOf(box) : 0"
        :height="box ? heightOf(box) : 0"
      />
      <g
        ref="thumb"
        class="ov-picture"
      />
      <rect
        v-for="mark in drawnMarks"
        :key="mark.id"
        :class="mark.selected ? 'ov-selected' : 'ov-reached'"
        :x="mark.at.left"
        :y="mark.at.top"
        :width="widthOf(mark.at)"
        :height="heightOf(mark.at)"
        data-testid="overview-mark"
      />
      <rect
        v-if="shown"
        class="ov-window"
        :x="shown.left"
        :y="shown.top"
        :width="widthOf(shown)"
        :height="heightOf(shown)"
        data-testid="overview-window"
      />
    </svg>
  </div>
</template>

<style scoped>
.diagram-overview {
  position: absolute; z-index: 2; overflow: hidden; background: var(--paper);
  border: 1px solid var(--border-strong); border-radius: 6px; box-shadow: var(--shadow);
  opacity: 0; pointer-events: none; transition: opacity 180ms ease-out;
}
.diagram-overview.corner { right: 10px; bottom: calc(var(--viewport-hint-height, 18px) + 10px); }
.diagram-overview.strip { left: 50%; bottom: calc(var(--viewport-hint-height, 18px) + 10px); transform: translateX(-50%); }
/* Shown while the reader is at the canvas: the pointer over it, or the keyboard inside it. */
.viewport-host:hover > .diagram-overview,
.viewport-host:focus-within > .diagram-overview { opacity: 1; pointer-events: auto; }
@media (prefers-reduced-motion: reduce) { .diagram-overview { transition: none; } }
@media print { .diagram-overview { display: none !important; } }
.diagram-overview svg { display: block; width: 100%; height: 100%; cursor: pointer; touch-action: none; }
.ov-paper { fill: var(--paper); }
.ov-picture { pointer-events: none; }
.ov-reached { fill: var(--paper-accent); fill-opacity: 0.55; }
.ov-selected {
  fill: var(--paper-accent); stroke: var(--paper-handle); stroke-width: 2px; vector-effect: non-scaling-stroke;
}
.ov-window {
  fill: var(--paper-accent); fill-opacity: 0.1; stroke: var(--paper-accent); stroke-width: 1.5px;
  vector-effect: non-scaling-stroke;
}
</style>
