<script setup lang="ts">
/**
 * The rule breaches the canvas marks over its lines (`labDrawing.breachMarksOf`): a halo round the
 * stretch that breaks a rule or a frame round each end, and the rule's name in a tag set off the line.
 */
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import type { BreachMark } from './labDrawing'
import { pointsAttribute } from './labDrawing'

defineProps<{ marks: readonly BreachMark[]; tagSize: number }>()
</script>

<template>
  <g class="lab-breaches">
    <g
      v-for="mark in marks"
      :key="mark.key"
      :class="`lab-breach-mark lab-breach--${mark.breach.tier}`"
      :data-rule="mark.breach.rule"
    >
      <title>{{ mark.tag }} ({{ mark.breach.tier }})</title>
      <polyline
        v-if="mark.breach.at.length >= 2"
        :points="pointsAttribute(mark.breach.at)"
        class="lab-breach-halo"
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
      <template v-if="mark.label">
        <line
          class="lab-breach-leader"
          :x1="mark.label.leader[0].x"
          :y1="mark.label.leader[0].y"
          :x2="mark.label.leader[1].x"
          :y2="mark.label.leader[1].y"
        />
        <rect
          class="lab-breach-tag-box"
          :x="mark.label.box.left"
          :y="mark.label.box.top"
          :width="widthOf(mark.label.box)"
          :height="heightOf(mark.label.box)"
          :rx="tagSize / 3"
        />
        <text
          class="lab-breach-tag"
          :x="mark.label.at.x"
          :y="mark.label.at.y"
          :font-size="tagSize"
        >
          {{ mark.tag }}
        </text>
      </template>
    </g>
  </g>
</template>

<style scoped>
/* A breach is an annotation, never line styling: a pale halo far wider than any line round the
   stretch that breaks the rule, or a dashed frame round each end, and the rule's name in a tag of its
   own set off the line, with a dotted leader back to it. */
.lab-breach-mark { --breach: var(--paper-error); }
.lab-breach-mark.lab-breach--soft { --breach: var(--paper-warn); }
.lab-breach-halo {
  fill: none; stroke: var(--breach); stroke-width: 16px; stroke-linecap: round; stroke-linejoin: round; opacity: 0.16;
}
.lab-breach-halo, .lab-breach-frame, .lab-breach-leader, .lab-breach-tag-box { vector-effect: non-scaling-stroke; }
.lab-breach-halo, .lab-breach-frame { pointer-events: stroke; }
.lab-breach-frame { fill: none; stroke: var(--breach); stroke-width: 2px; stroke-dasharray: 5 3; opacity: 0.8; }
.lab-breach-leader { stroke: var(--breach); stroke-width: 1px; stroke-dasharray: 1 2; pointer-events: none; }
.lab-breach-tag-box { fill: var(--paper-handle); stroke: var(--breach); stroke-width: 1px; pointer-events: none; }
.lab-breach-tag {
  fill: var(--breach); text-anchor: middle; font-family: system-ui, sans-serif; font-weight: 600; pointer-events: none;
}
</style>
