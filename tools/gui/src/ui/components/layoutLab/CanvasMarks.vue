<script setup lang="ts">
/**
 * What the canvas marks while a picture is arranged, refusing nothing (D6, Q12): an element a shape
 * painted after it covers, and two connected elements over each other (`canvasMarks`). Each mark says
 * in its tooltip what it means; Save stays available and the verifier reports what is left.
 */
import { computed } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import type { ArrangementSession } from '../../composables/useArrangementSession'
import { hiddenElements, overlappingEnds } from './canvasMarks'

/** *order*: the shapes by alias, back to front, as the canvas paints them. */
const props = defineProps<{ session: ArrangementSession; order: readonly string[] }>()

const hidden = computed((): Extent[] => {
  const drawn = props.session.geometry.value
  const where = props.session.placement.value
  if (!drawn || !where) return []
  const insideOf = new Map([...drawn.boxes, ...drawn.elements].map((shape) => [shape.alias, shape.inside]))
  return hiddenElements(props.order, where, insideOf).flatMap((alias) => where.elements.get(alias) ?? [])
})

const overlapping = computed((): Extent[] => {
  const drawn = props.session.geometry.value
  const where = props.session.placement.value
  if (!drawn || !where) return []
  const relations = new Map(drawn.relations.map((relation) => [relation.index, relation]))
  return [...overlappingEnds(props.session.breaches.value)].flatMap((index) => {
    const relation = relations.get(index)
    return relation ? [relation.source, relation.target].flatMap((alias) => where.elements.get(alias) ?? []) : []
  })
})
</script>

<template>
  <g
    class="canvas-marks"
    data-testid="canvas-marks"
  >
    <rect
      v-for="(extent, index) in hidden"
      :key="`hidden:${index}`"
      class="mark-hidden"
      :x="extent.left - 3"
      :y="extent.top - 3"
      :width="widthOf(extent) + 6"
      :height="heightOf(extent) + 6"
    >
      <title>Hidden: a box or element covers it here. Move it, or bring it forward.</title>
    </rect>
    <rect
      v-for="(extent, index) in overlapping"
      :key="`overlap:${index}`"
      class="mark-overlap"
      :x="extent.left"
      :y="extent.top"
      :width="widthOf(extent)"
      :height="heightOf(extent)"
    >
      <title>Connected elements overlap: no line can join them. Save still works; the verifier reports it.</title>
    </rect>
  </g>
</template>

<style scoped>
.canvas-marks rect { vector-effect: non-scaling-stroke; pointer-events: none; }
.mark-hidden { fill: none; stroke: #d97706; stroke-width: 1.5px; stroke-dasharray: 4 3; }
.mark-overlap {
  fill: #dc2626; fill-opacity: 0.08; stroke: #dc2626; stroke-width: 1.5px; stroke-dasharray: 2 2;
}
</style>
