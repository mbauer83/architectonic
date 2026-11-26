<script setup lang="ts">
/**
 * What the canvas draws for a selected line (sketch 02·3–02·5): its course outlined, a green-edged diamond at
 * each end to slide it along its element, a handle in the middle of each segment to move it sideways,
 * a white handle on each bend, and — while its label is moved — a leader from the label to its anchor.
 * Every handle is the same size on screen however far the picture is zoomed.
 */
import { computed } from 'vue'
import type { Point } from '../../../domain/layout/geometry'
import { distanceBetween } from '../../../domain/layout/geometry'
import type { LabelAnchor } from '../../../domain/layout/orthogonal'
import { pointAlong } from '../../../domain/layout/orthogonal'
import type { End } from '../../../domain/layout/canvasRouteEdits'
import { labelCentre } from '../../../domain/layout/canvasRouteEdits'
import { pointsAttribute } from './canvasDrawing'

const props = defineProps<{
  line: number
  course: readonly Point[]
  bends: readonly Point[]
  picked: number | null
  anchor: LabelAnchor | null
  leader: boolean
  handleSide: number
}>()
const emit = defineEmits<{
  end: [event: PointerEvent, end: End]
  segment: [event: PointerEvent, index: number]
  bend: [event: PointerEvent, index: number]
  removeBend: [event: MouseEvent, index: number]
  addBend: [event: MouseEvent]
}>()

/** An end's diamond is a little larger than the other handles: 10 screen pixels to their 9 (sketch 02·3). */
const END_SCALE = 10 / 9
const endSide = computed(() => props.handleSide * END_SCALE)
const ends = computed((): [End, Point][] => [['from', props.course[0]], ['to', props.course[props.course.length - 1]]])
/** The middle of each segment long enough to take a handle of its own. */
const middles = computed(() => props.course.slice(1).flatMap((end, index) => {
  const start = props.course[index]
  return distanceBetween(start, end) >= 2 * props.handleSide
    ? [{ index, at: { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 }, level: Math.abs(start.y - end.y) < 0.5 }]
    : []
}))
const leaderLine = computed(() => {
  if (!props.leader || !props.anchor) return null
  return { from: pointAlong(props.course, props.anchor.at), to: labelCentre(props.course, props.anchor) }
})
</script>

<template>
  <g
    class="lab-line-handles"
    :data-selected-line="line"
  >
    <polyline
      class="lab-line-handles__course"
      :points="pointsAttribute(course)"
      @dblclick="emit('addBend', $event)"
    />
    <template v-if="leaderLine">
      <line
        class="lab-line-handles__leader"
        :x1="leaderLine.from.x"
        :y1="leaderLine.from.y"
        :x2="leaderLine.to.x"
        :y2="leaderLine.to.y"
      />
      <circle
        class="lab-line-handles__anchor"
        :cx="leaderLine.from.x"
        :cy="leaderLine.from.y"
        :r="handleSide / 3"
      />
    </template>
    <rect
      v-for="{ index, at, level } in middles"
      :key="`segment-${index}`"
      :class="['lab-line-handles__segment', level ? 'is-level' : 'is-upright']"
      :data-segment="index"
      :x="at.x - (level ? handleSide : handleSide / 2) / 2"
      :y="at.y - (level ? handleSide / 2 : handleSide) / 2"
      :width="level ? handleSide : handleSide / 2"
      :height="level ? handleSide / 2 : handleSide"
      @pointerdown="emit('segment', $event, index)"
      @dblclick="emit('addBend', $event)"
    />
    <circle
      v-for="(at, index) in bends"
      :key="`bend-${index}`"
      :class="['lab-line-handles__bend', { 'is-picked': index === picked }]"
      :data-bend="index"
      :cx="at.x"
      :cy="at.y"
      :r="handleSide / 2"
      @pointerdown="emit('bend', $event, index)"
      @dblclick="emit('removeBend', $event, index)"
    />
    <rect
      v-for="[end, at] in ends"
      :key="end"
      class="lab-line-handles__end"
      :data-end="end"
      :x="at.x - endSide / 2"
      :y="at.y - endSide / 2"
      :width="endSide"
      :height="endSide"
      :transform="`rotate(45 ${at.x} ${at.y})`"
      @pointerdown="emit('end', $event, end)"
    />
  </g>
</template>

<style scoped>
/* The sketch kit's route handles: the selected course in the accent colour, green diamonds at the
   ends, white bends and segment handles outlined in the accent colour. */
.lab-line-handles__course {
  fill: none; stroke: var(--paper-accent); stroke-width: 2px; opacity: 0.55; pointer-events: stroke;
  vector-effect: non-scaling-stroke;
}
/* An end is a white diamond outlined in green, which slides along its element: the crosshair says so. */
.lab-line-handles__end { fill: var(--paper-handle); stroke: var(--paper-port); stroke-width: 1.5px; cursor: crosshair; }
.lab-line-handles__bend { fill: var(--paper-handle); stroke: var(--paper-accent); stroke-width: 1.5px; cursor: move; }
.lab-line-handles__bend.is-picked { fill: var(--paper-accent); }
.lab-line-handles__segment { fill: var(--paper-handle); stroke: var(--paper-accent); stroke-width: 1.5px; }
.lab-line-handles__segment.is-level { cursor: ns-resize; }
.lab-line-handles__segment.is-upright { cursor: ew-resize; }
.lab-line-handles__end, .lab-line-handles__bend, .lab-line-handles__segment { vector-effect: non-scaling-stroke; }
.lab-line-handles__leader {
  stroke: var(--paper-accent);
  stroke-width: 1px;
  stroke-dasharray: 2 2;
  pointer-events: none;
  vector-effect: non-scaling-stroke;
}
.lab-line-handles__anchor { fill: var(--paper-accent); pointer-events: none; }
</style>
