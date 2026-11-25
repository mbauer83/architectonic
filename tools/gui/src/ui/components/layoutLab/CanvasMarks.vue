<script setup lang="ts">
/**
 * What the canvas marks while a picture is arranged, refusing nothing (D6, Q12): an element a shape
 * painted after it covers — a dashed amber outline and "⚠ hidden behind …" — and two connected elements
 * over each other — both outlined in red and "✕ connected elements overlap — no route" (`canvasMarks`).
 * Always shown, in words at the same size on screen at any zoom, so colour never carries them alone;
 * Save stays available and the verifier reports what is left.
 */
import { computed } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import type { ArrangementSession } from '../../composables/useArrangementSession'
import { hiddenElements, overlappingEnds } from './canvasMarks'

/**
 * *order*: the shapes by alias, back to front, as the canvas paints them; *pixel*: one screen pixel;
 * *moving*: a shape is being dragged, and the marks stay as they were until it is dropped.
 */
const props = defineProps<{
  session: ArrangementSession; order: readonly string[]; pixel: number; moving?: boolean
  /** A shape's name in the model, as the list of changes names it; absent, the label the picture draws. */
  nameOf?: (alias: string) => string
}>()

interface Mark {
  readonly key: string
  readonly outlined: readonly Extent[]
  readonly words: string
  /** Where the tag sits: above this point, or below it. */
  readonly at: { readonly x: number; readonly y: number; readonly below?: boolean }
}

const nameOf = (alias: string): string => {
  if (props.nameOf) return props.nameOf(alias)
  const drawn = props.session.geometry.value
  return drawn?.elements.find((one) => one.alias === alias)?.label
    ?? drawn?.boxes.find((one) => one.alias === alias)?.label ?? alias
}

const hidden = computed((): Mark[] => {
  const drawn = props.session.geometry.value
  const where = props.session.placement.value
  if (!drawn || !where) return []
  const insideOf = new Map([...drawn.boxes, ...drawn.elements].map((shape) => [shape.alias, shape.inside]))
  return hiddenElements(props.order, where, insideOf).flatMap(({ alias, by }) => {
    const extent = where.elements.get(alias)
    return extent ? [{
      key: `hidden:${alias}`, outlined: [extent], words: `⚠ hidden behind ${nameOf(by)}`,
      at: { x: extent.left, y: extent.top },
    }] : []
  })
})

const overlapping = computed((): Mark[] => {
  const drawn = props.session.geometry.value
  const where = props.session.placement.value
  if (!drawn || !where) return []
  const relations = new Map(drawn.relations.map((relation) => [relation.index, relation]))
  return [...overlappingEnds(props.session.breaches.value)].flatMap((index) => {
    const relation = relations.get(index)
    const ends = relation ? [relation.source, relation.target].flatMap((alias) => where.elements.get(alias) ?? []) : []
    return ends.length === 2 ? [{
      key: `overlap:${index}`, outlined: ends, words: '✕ connected elements overlap — no route',
      at: { x: Math.min(ends[0].left, ends[1].left), y: Math.max(ends[0].bottom, ends[1].bottom), below: true },
    }] : []
  })
})

/** A tag's size on screen: eleven-pixel words in a seventeen-pixel band, whatever the zoom. */
const FONT = 11
const BAND = 17
const tagOf = (mark: Mark) => {
  const font = FONT * props.pixel
  const height = BAND * props.pixel
  const gap = 3 * props.pixel
  return {
    x: mark.at.x, y: mark.at.below ? mark.at.y + gap : mark.at.y - height - gap,
    width: mark.words.length * font * 0.6 + 12 * props.pixel, height, font, rx: 3 * props.pixel,
  }
}

/** The marks as they were when the drag began, while it lasts: found on the drop, not on every frame. */
let found: readonly Mark[] = []
const marks = computed((): readonly Mark[] => {
  if (!props.moving) found = [...hidden.value, ...overlapping.value]
  return found
})
</script>

<template>
  <g
    class="canvas-marks"
    data-testid="canvas-marks"
  >
    <g
      v-for="mark in marks"
      :key="mark.key"
      :class="mark.key.startsWith('hidden') ? 'mark-hidden' : 'mark-overlap'"
      :data-mark="mark.key"
    >
      <rect
        v-for="(extent, index) in mark.outlined"
        :key="index"
        class="mark-outline"
        :x="extent.left"
        :y="extent.top"
        :width="widthOf(extent)"
        :height="heightOf(extent)"
      />
      <rect
        class="mark-tag"
        :x="tagOf(mark).x"
        :y="tagOf(mark).y"
        :width="tagOf(mark).width"
        :height="tagOf(mark).height"
        :rx="tagOf(mark).rx"
      />
      <text
        class="mark-words"
        :x="tagOf(mark).x + 5 * pixel"
        :y="tagOf(mark).y + tagOf(mark).height - 5 * pixel"
        :font-size="tagOf(mark).font"
      >
        {{ mark.words }}
      </text>
    </g>
  </g>
</template>

<style scoped>
.canvas-marks rect { vector-effect: non-scaling-stroke; pointer-events: none; }
.canvas-marks text { pointer-events: none; font-family: system-ui, sans-serif; font-weight: 600; }
.mark-hidden .mark-outline { fill: none; stroke: var(--paper-warn); stroke-width: 1.5px; stroke-dasharray: 4 3; }
.mark-overlap .mark-outline {
  fill: var(--paper-error); fill-opacity: 0.08; stroke: var(--paper-error); stroke-width: 1.5px; stroke-dasharray: 2 2;
}
.mark-tag { stroke-width: 1px; }
.mark-hidden .mark-tag { fill: var(--paper-warn-soft); stroke: var(--paper-warn); }
.mark-hidden .mark-words { fill: var(--paper-warn-text); }
.mark-overlap .mark-tag { fill: var(--paper-error-soft); stroke: var(--paper-error); }
.mark-overlap .mark-words { fill: var(--paper-error-text); }
</style>
