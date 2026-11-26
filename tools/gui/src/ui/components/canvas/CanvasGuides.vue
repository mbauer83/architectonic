<script setup lang="ts">
/**
 * The alignment guides of a move or resize (sketch 02·1): a dashed line where an edge or a centre lines up
 * with a neighbour's, across both shapes. Drawn only while the gesture has them, gone 0.7 s after the drop.
 */
import type { Guide } from '../../../domain/layout/canvasSnapping'

defineProps<{ guides: readonly Guide[] }>()
</script>

<template>
  <g
    class="lab-guides"
    aria-hidden="true"
  >
    <line
      v-for="(guide, index) in guides"
      :key="index"
      class="lab-guide"
      data-testid="alignment-guide"
      :x1="guide.axis === 'x' ? guide.at : guide.from"
      :x2="guide.axis === 'x' ? guide.at : guide.to"
      :y1="guide.axis === 'x' ? guide.from : guide.at"
      :y2="guide.axis === 'x' ? guide.to : guide.at"
    />
  </g>
</template>

<style scoped>
.lab-guide {
  stroke: var(--paper-guide); stroke-width: 1px; stroke-dasharray: 4 3; pointer-events: none;
  vector-effect: non-scaling-stroke;
}
</style>
