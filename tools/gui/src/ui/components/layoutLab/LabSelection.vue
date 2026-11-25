<script setup lang="ts">
/**
 * What the canvas draws for the selection: a frame round each selected shape, the eight handles when
 * one shape is selected and the picture may be changed, and the selection rectangle while it is swept —
 * dashed when it selects what it touches, solid when only what it encloses (sketch 01·5, D20).
 */
import { computed } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
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
}>()
const emit = defineEmits<{ handle: [event: PointerEvent, handle: Handle] }>()

const frames = computed((): { alias: string; extent: Extent }[] => {
  const where = props.placement
  if (!where) return []
  return props.selection.flatMap((alias) => {
    const extent = where.elements.get(alias) ?? where.boxes.get(alias)
    return extent ? [{ alias, extent }] : []
  })
})

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
  (!props.readonly && frames.value.length === 1 ? frames.value[0].extent : null))
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
      :data-selected="alias"
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
.lab-handles__handle--n, .lab-handles__handle--s { cursor: ns-resize; }
.lab-handles__handle--e, .lab-handles__handle--w { cursor: ew-resize; }
.lab-handles__handle--ne, .lab-handles__handle--sw { cursor: nesw-resize; }
.lab-handles__handle--nw, .lab-handles__handle--se { cursor: nwse-resize; }
/* The selection rectangle shows what it selects while it is drawn: dashed, every element it touches;
   solid, only what it encloses. */
.lab-rectangle { fill: var(--paper-accent-soft); stroke: var(--paper-accent); stroke-width: 1px; pointer-events: none; }
.lab-rectangle--touches { stroke-dasharray: 4 3; }
/* Keyboard focus: a dashed ring, apart from the selection's outline. */
.lab-focus-ring {
  fill: none; stroke: var(--paper-accent); stroke-width: 1.5px; stroke-dasharray: 3 3; pointer-events: none;
  vector-effect: non-scaling-stroke;
}
</style>
