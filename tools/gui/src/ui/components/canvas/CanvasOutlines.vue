<script setup lang="ts">
/**
 * Shapes something outside the canvas points at, outlined where they are now: the two ends a panel row
 * would connect, while the row is hovered or focused (sketch 01·8). Drawn over the picture, never in the
 * way of a press.
 */
import { computed } from 'vue'
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import type { ArrangementSession } from '../../composables/useArrangementSession'

const props = defineProps<{ session: ArrangementSession; aliases: readonly string[] }>()

/** A little outside the shape, so its own outline stays visible inside the mark. */
const MARGIN = 4

const outlines = computed(() => {
  const where = props.session.placement.value
  return where ? props.aliases.flatMap((alias) => {
    const extent = where.elements.get(alias) ?? where.boxes.get(alias)
    return extent ? [{
      alias, x: extent.left - MARGIN, y: extent.top - MARGIN,
      width: widthOf(extent) + 2 * MARGIN, height: heightOf(extent) + 2 * MARGIN,
    }] : []
  }) : []
})
</script>

<template>
  <g
    class="canvas-outlines"
    data-testid="canvas-outlines"
  >
    <rect
      v-for="one in outlines"
      :key="one.alias"
      :data-outlined="one.alias"
      :x="one.x"
      :y="one.y"
      :width="one.width"
      :height="one.height"
      rx="4"
    />
  </g>
</template>

<style scoped>
.canvas-outlines rect {
  fill: var(--paper-accent-soft); fill-opacity: .35; stroke: var(--paper-accent); stroke-width: 2.5px;
  vector-effect: non-scaling-stroke; pointer-events: none;
}
</style>
