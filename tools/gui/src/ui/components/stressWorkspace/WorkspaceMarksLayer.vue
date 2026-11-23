<script setup lang="ts">
/**
 * The workspace's marks, drawn inside the diagram canvas over the elements they are about: what steps
 * back, what the focus hits, what a candidate changed. Shared by the reading canvas and the sketching
 * canvas, so a mark looks the same on both.
 */
import { computed } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import type { Marks } from '../../../domain/stressAnalysis/workspaceMarks'
import type { ArrangementSession } from '../../composables/useArrangementSession'

const props = defineProps<{
  session: ArrangementSession
  /** Each drawn element's entity, by alias, as its stable id. */
  entityOf: ReadonlyMap<string, string>
  marks: Marks
  dimmed?: ReadonlySet<string>
  /** A tag's font size in drawing units, so it reads the same on screen at any zoom. */
  tagSize: number
}>()

const drawn = (filter: (stableId: string) => boolean): { alias: string; extent: Extent; stableId: string }[] => {
  const where = props.session.placement.value
  return [...props.entityOf].flatMap(([alias, stableId]) => {
    const extent = where?.elements.get(alias)
    return extent && filter(stableId) ? [{ alias, extent, stableId }] : []
  })
}
const marked = computed(() => drawn((id) => props.marks.has(id)).flatMap((one) => {
  const mark = props.marks.get(one.stableId)
  return mark ? [{ ...one, mark }] : []
}))
const stepped = computed(() => drawn((id) => props.dimmed?.has(id) ?? false))
</script>

<template>
  <g class="ws-marks">
    <rect
      v-for="one in stepped"
      :key="`dim:${one.alias}`"
      class="ws-dim"
      :x="one.extent.left - 2"
      :y="one.extent.top - 2"
      :width="widthOf(one.extent) + 4"
      :height="heightOf(one.extent) + 4"
    />
    <g
      v-for="one in marked"
      :key="`mark:${one.alias}`"
      :class="`ws-mark ws-mark--${one.mark.kind}`"
      :data-marked="one.stableId"
    >
      <title>{{ one.mark.title }}</title>
      <rect
        class="ws-mark-frame"
        :x="one.extent.left - 3"
        :y="one.extent.top - 3"
        :width="widthOf(one.extent) + 6"
        :height="heightOf(one.extent) + 6"
        rx="4"
      />
      <text
        class="ws-mark-tag"
        :x="one.extent.right + 2"
        :y="one.extent.top - 4"
        :font-size="tagSize"
      >
        {{ one.mark.tag }}
      </text>
    </g>
  </g>
</template>

<style scoped>
.ws-marks { pointer-events: none; }
.ws-dim { fill: #fff; fill-opacity: 0.72; }
.ws-mark-frame { fill: none; stroke-width: 2.5px; vector-effect: non-scaling-stroke; }
.ws-mark-tag {
  font-family: system-ui, sans-serif; font-weight: 700; paint-order: stroke; stroke: #fff; stroke-width: 0.3em;
  stroke-linejoin: round;
}
.ws-mark--hit .ws-mark-frame { stroke: #1e293b; }
.ws-mark--hit .ws-mark-tag { fill: #1e293b; }
.ws-mark--added .ws-mark-frame { stroke: #15803d; }
.ws-mark--added .ws-mark-tag { fill: #15803d; }
.ws-mark--edited .ws-mark-frame { stroke: #b45309; }
.ws-mark--edited .ws-mark-tag { fill: #b45309; }
.ws-mark--removed .ws-mark-frame { stroke: #b91c1c; stroke-dasharray: 5 3; fill: #fff; fill-opacity: 0.6; }
.ws-mark--removed .ws-mark-tag { fill: #b91c1c; }
.ws-mark--framed .ws-mark-frame { stroke: var(--accent); stroke-width: 3px; }
</style>
