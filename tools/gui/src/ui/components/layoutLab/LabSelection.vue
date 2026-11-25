<script setup lang="ts">
/**
 * What the canvas draws for the selection: a frame round each selected box — an element's own outline
 * turns blue instead (`LayoutLabCanvas`), so there is one selection look and no second frame (01·3) —
 * the eight handles when one shape is selected and the picture may be changed, with the relation dot
 * beside a selected element to draw a relation from (03·8), and the selection rectangle while it is
 * swept — dashed when it selects what it touches, solid when only what it encloses (sketch 01·5, D20).
 */
import { computed } from 'vue'
import type { Extent, Point } from '../../../domain/layout/geometry'
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import type { Handle } from '../../../domain/layout/lab/labArrangement'
import type { Placement } from '../../../domain/layout/lab/labRouting'
import type { RectangleRule } from '../../../domain/layout/lab/labSelection'
import { handlesOf } from './labDrawing'

const props = defineProps<{
  placement: Placement | null
  selection: readonly string[]
  rectangle: Extent | null
  /** What the rectangle selects, which its border shows. */
  rule?: RectangleRule
  handleSide: number
  readonly?: boolean
  /** The shape the keyboard is on, ringed while the keyboard is in use (sketch 01·3); and a screen pixel. */
  ring?: Extent | null
  pixel?: number
  /** The bends a selection rectangle picked up, marked as selected (sketch 02·8). */
  bends?: readonly Point[]
}>()
const emit = defineEmits<{ handle: [event: PointerEvent, handle: Handle] }>()

const selected = computed((): { alias: string; extent: Extent; box: boolean }[] => {
  const where = props.placement
  if (!where) return []
  return props.selection.flatMap((alias) => {
    const element = where.elements.get(alias)
    const extent = element ?? where.boxes.get(alias)
    return extent ? [{ alias, extent, box: element === undefined }] : []
  })
})
const frames = computed(() => selected.value.filter((one) => one.box))

/** The focus ring stands a few screen pixels off the shape, so it never reads as the shape's outline. */
const RING_OFFSET = 5
const ringed = computed((): Extent | null => {
  const offset = RING_OFFSET * (props.pixel ?? 1)
  const at = props.ring
  return at
    ? { left: at.left - offset, top: at.top - offset, right: at.right + offset, bottom: at.bottom + offset }
    : null
})

const resizable = computed((): Extent | null =>
  (!props.readonly && selected.value.length === 1 ? selected.value[0].extent : null))

/** How far right of a selected element its relation dot stands, and how large it is, in screen pixels. */
const DOT_OFFSET = 14
const DOT_RADIUS = 6
const dot = computed(() => {
  const [one] = selected.value
  const pixel = props.pixel ?? 1
  return resizable.value && !one.box ? {
    alias: one.alias, x: one.extent.right + DOT_OFFSET * pixel, y: (one.extent.top + one.extent.bottom) / 2,
    r: DOT_RADIUS * pixel,
  } : null
})
</script>

<template>
  <g
    v-if="!readonly"
    class="lab-handles"
  >
    <rect
      v-for="{ alias, extent } in frames"
      :key="alias"
      :x="extent.left"
      :y="extent.top"
      :width="widthOf(extent)"
      :height="heightOf(extent)"
      class="lab-handles__frame"
    />
    <template v-if="resizable">
      <rect
        v-for="{ handle, at } in handlesOf(resizable)"
        :key="handle"
        :x="at.x - handleSide / 2"
        :y="at.y - handleSide / 2"
        :width="handleSide"
        :height="handleSide"
        :class="`lab-handles__handle lab-handles__handle--${handle}`"
        :data-handle="handle"
        @pointerdown="emit('handle', $event, handle)"
      />
    </template>
    <!-- Its own target, never a modifier: a drag from it draws a relation, as from the element's edge. -->
    <circle
      v-if="dot"
      class="lab-handles__relation"
      data-testid="relation-dot"
      :data-relation-from="dot.alias"
      :cx="dot.x"
      :cy="dot.y"
      :r="dot.r"
    >
      <title>Draw a relation</title>
    </circle>
    <circle
      v-for="(at, index) in bends ?? []"
      :key="`bend-${index}`"
      class="lab-handles__bend-selected"
      data-testid="selected-bend"
      :cx="at.x"
      :cy="at.y"
      :r="5 * (pixel ?? 1)"
    />
    <rect
      v-if="ringed"
      class="lab-focus-ring"
      data-testid="focus-ring"
      :x="ringed.left"
      :y="ringed.top"
      :width="widthOf(ringed)"
      :height="heightOf(ringed)"
      :rx="4 * (pixel ?? 1)"
    />
    <rect
      v-if="rectangle"
      :class="['lab-rectangle', `lab-rectangle--${rule ?? 'encloses'}`]"
      data-testid="selection-rectangle"
      :data-rule="rule ?? 'encloses'"
      :x="rectangle.left"
      :y="rectangle.top"
      :width="widthOf(rectangle)"
      :height="heightOf(rectangle)"
    />
  </g>
</template>

<style scoped>
.lab-handles__frame { fill: none; stroke: var(--paper-accent); stroke-width: 1.5px; pointer-events: none; }
.lab-handles__frame, .lab-handles__handle, .lab-rectangle { vector-effect: non-scaling-stroke; }
.lab-handles__handle { fill: var(--paper-handle); stroke: var(--paper-accent); stroke-width: 1.5px; }
.lab-handles__relation {
  fill: var(--paper-rule); stroke: var(--paper-handle); stroke-width: 2px; cursor: crosshair;
  vector-effect: non-scaling-stroke;
}
.lab-handles__relation:hover { fill: var(--paper-accent); }
.lab-handles__handle--n, .lab-handles__handle--s { cursor: ns-resize; }
.lab-handles__handle--e, .lab-handles__handle--w { cursor: ew-resize; }
.lab-handles__handle--ne, .lab-handles__handle--sw { cursor: nesw-resize; }
.lab-handles__handle--nw, .lab-handles__handle--se { cursor: nwse-resize; }
/* The selection rectangle shows what it selects while it is drawn: dashed, every element it touches;
   solid, only what it encloses. */
.lab-rectangle { fill: var(--paper-accent-soft); stroke: var(--paper-accent); stroke-width: 1px; pointer-events: none; }
.lab-rectangle--touches { stroke-dasharray: 4 3; }
.lab-handles__bend-selected {
  fill: var(--paper-accent); stroke: var(--paper-handle); stroke-width: 1.5px; pointer-events: none;
  vector-effect: non-scaling-stroke;
}
/* Keyboard focus: a dashed ring, apart from the selection's outline. */
.lab-focus-ring {
  fill: none; stroke: var(--paper-accent); stroke-width: 1.5px; stroke-dasharray: 3 3; pointer-events: none;
  vector-effect: non-scaling-stroke;
}
</style>
