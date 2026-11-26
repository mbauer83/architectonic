<script setup lang="ts">
/**
 * The layout rule breaches the canvas marks while its layout is checked (`canvasDrawing.breachMarksOf`):
 * a thin dashed band along the stretch that breaks a rule, or a thin dashed outline round each end, and
 * what is broken said on hover. Quiet by design (owner): no tints, no words on the picture.
 */
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import { breachSentence } from '../../../domain/layout/canvasBreaches'
import type { LayoutGeometry } from '../../../domain/schemas/diagramLayoutGeometry'
import type { BreachMark } from './canvasDrawing'
import { pointsAttribute } from './canvasDrawing'

defineProps<{ marks: readonly BreachMark[]; geometry: LayoutGeometry | null }>()
</script>

<template>
  <g
    class="lab-breaches"
    data-testid="layout-breaches"
  >
    <g
      v-for="mark in marks"
      :key="mark.key"
      :class="`lab-breach-mark lab-breach--${mark.breach.tier}`"
      :data-rule="mark.breach.rule"
    >
      <title>{{ breachSentence(mark.breach, geometry) }}</title>
      <polyline
        v-if="mark.breach.at.length >= 2"
        :points="pointsAttribute(mark.breach.at)"
        class="lab-breach-band"
      />
      <rect
        v-for="(extent, end) in mark.frames"
        :key="end"
        :x="extent.left - 3"
        :y="extent.top - 3"
        :width="widthOf(extent) + 6"
        :height="heightOf(extent) + 6"
        class="lab-breach-frame"
      />
    </g>
  </g>
</template>

<style scoped>
/* An annotation, never line styling: a band wider than the line, thin and dashed, and an outline round
   an end. Neither fills anything. */
.lab-breach-mark { --breach: var(--paper-error); }
.lab-breach-mark.lab-breach--soft { --breach: var(--paper-warn); }
.lab-breach-band {
  fill: none; stroke: var(--breach); stroke-width: 6px; stroke-dasharray: 2 3; stroke-linecap: butt;
  opacity: 0.45;
}
.lab-breach-frame { fill: none; stroke: var(--breach); stroke-width: 1px; stroke-dasharray: 4 3; opacity: 0.8; }
.lab-breach-band, .lab-breach-frame { vector-effect: non-scaling-stroke; pointer-events: stroke; }
</style>
