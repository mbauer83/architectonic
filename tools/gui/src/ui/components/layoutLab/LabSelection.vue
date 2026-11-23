<script setup lang="ts">
/**
 * What the canvas draws for the selection: a frame round each selected shape, the eight handles when
 * one shape is selected and the picture may be changed, and the selection rectangle while it is swept.
 */
import { computed } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import type { Handle } from '../../../domain/layout/lab/labArrangement'
import type { Placement } from '../../../domain/layout/lab/labRouting'
import { handlesOf } from './labDrawing'

const props = defineProps<{
  placement: Placement | null
  selection: readonly string[]
  rectangle: Extent | null
  handleSide: number
  readonly?: boolean
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
      v-if="rectangle"
      class="lab-rectangle"
      data-testid="selection-rectangle"
      :x="rectangle.left"
      :y="rectangle.top"
      :width="widthOf(rectangle)"
      :height="heightOf(rectangle)"
    />
  </g>
</template>

<style scoped>
.lab-handles__frame { fill: none; stroke: var(--accent); stroke-width: 1.5px; pointer-events: none; }
.lab-handles__frame, .lab-handles__handle, .lab-rectangle { vector-effect: non-scaling-stroke; }
.lab-handles__handle { fill: #fff; stroke: var(--accent); stroke-width: 1.5px; }
.lab-handles__handle--n, .lab-handles__handle--s { cursor: ns-resize; }
.lab-handles__handle--e, .lab-handles__handle--w { cursor: ew-resize; }
.lab-handles__handle--ne, .lab-handles__handle--sw { cursor: nesw-resize; }
.lab-handles__handle--nw, .lab-handles__handle--se { cursor: nwse-resize; }
/* The rectangle that selects what it encloses: dashed, so it reads as a gesture, not a shape. */
.lab-rectangle {
  fill: rgba(37, 99, 235, 0.06); stroke: var(--accent); stroke-width: 1px; stroke-dasharray: 4 3; pointer-events: none;
}
</style>
