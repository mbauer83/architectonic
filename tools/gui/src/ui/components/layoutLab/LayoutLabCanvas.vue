<script setup lang="ts">
/**
 * The lab's picture: boxes, elements and lines drawn from the real geometry where they are now, with
 * the rule breaches over them and handles on the selected shape. Press and drag a shape to move it; a
 * box carries what it holds. Drag a handle to resize.
 */
import { computed, ref, watch } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import { pointAlong } from '../../../domain/layout/orthogonal'
import type { LayoutLab } from '../../composables/useLayoutLab'
import type { PlacedWord } from './labDrawing'
import { elementWords, handlesOf, paintOrder, pointsAttribute, titleWords } from './labDrawing'
import { useLabGesture } from './useLabGesture'

const props = defineProps<{ lab: LayoutLab; showBreaches: boolean }>()

const svg = ref<SVGSVGElement | null>(null)
const gesture = useLabGesture(props.lab, svg)

/** Room round the drawing, so a shape dragged out of it stays in reach. */
const MARGIN = 40

const geometry = computed(() => props.lab.geometry.value)
const placement = computed(() => props.lab.placement.value)

/** What is drawn now, shapes and lines: the view fits it, not PlantUML's page with its title. */
const drawnExtent = computed((): Extent | null => {
  const where = placement.value
  if (!where) return null
  const points = [...props.lab.courses.value.values()].flat()
  const all: Extent[] = [
    ...where.elements.values(),
    ...where.boxes.values(),
    ...points.map((point) => ({ left: point.x, top: point.y, right: point.x, bottom: point.y })),
  ]
  if (all.length === 0) return null
  return {
    left: Math.min(...all.map((extent) => extent.left)) - MARGIN,
    top: Math.min(...all.map((extent) => extent.top)) - MARGIN,
    right: Math.max(...all.map((extent) => extent.right)) + MARGIN,
    bottom: Math.max(...all.map((extent) => extent.bottom)) + MARGIN,
  }
})

/**
 * The view: what is drawn, refitted after every change but held still while something is dragged, so
 * the point under the pointer keeps meaning the same place on the picture.
 */
const view = ref<Extent | null>(null)
watch(drawnExtent, (now) => { if (!gesture.dragging.value || !view.value) view.value = now }, { immediate: true })
watch(() => gesture.dragging.value, (dragging) => { if (!dragging) view.value = drawnExtent.value })

const viewBox = computed(() => {
  const extent = view.value
  return extent ? `${extent.left} ${extent.top} ${widthOf(extent)} ${heightOf(extent)}` : '0 0 100 100'
})

const aspect = computed(() => {
  const extent = view.value
  return extent ? `${widthOf(extent)} / ${heightOf(extent)}` : '1 / 1'
})

interface DrawnShape {
  readonly alias: string
  readonly isBox: boolean
  readonly kind: string
  readonly now: Extent
  readonly words: PlacedWord[]
}

/** Every shape back to front, each where it is now with its text. */
const shapes = computed((): DrawnShape[] => {
  const drawn = geometry.value
  const where = placement.value
  if (!drawn || !where) return []
  const boxes = new Map(drawn.boxes.map((box) => [box.alias, box]))
  const elements = new Map(drawn.elements.map((element) => [element.alias, element]))
  return paintOrder(drawn, gesture.lifted.value).flatMap(({ alias, isBox }): DrawnShape[] => {
    const box = boxes.get(alias)
    const element = elements.get(alias)
    const now = isBox ? where.boxes.get(alias) : where.elements.get(alias)
    if (!now) return []
    if (box) return [{ alias, isBox, kind: box.kind, now, words: titleWords(box, now) }]
    if (element) {
      return [{ alias, isBox, kind: 'element', now, words: elementWords(element.words, element.extent, now) }]
    }
    return []
  })
})

const lines = computed(() => {
  const drawn = geometry.value
  if (!drawn) return []
  return drawn.relations.flatMap((relation) => {
    const course = props.lab.courses.value.get(relation.index)
    if (!course || course.length < 2) return []
    return [{ relation, points: pointsAttribute(course), labelAt: pointAlong(course, 0.5) }]
  })
})

const marks = computed(() => (props.showBreaches ? props.lab.breaches.value : []))

const ends = (relationIndex: number): Extent[] => {
  const relation = geometry.value?.relations.find((one) => one.index === relationIndex)
  const where = placement.value
  if (!relation || !where) return []
  return [relation.source, relation.target].flatMap((alias) => {
    const extent = where.elements.get(alias) ?? where.boxes.get(alias)
    return extent ? [extent] : []
  })
}

const selectedExtent = computed((): Extent | null => {
  const alias = gesture.selected.value
  const where = placement.value
  return alias && where ? (where.elements.get(alias) ?? where.boxes.get(alias) ?? null) : null
})
</script>

<template>
  <svg
    ref="svg"
    class="lab-canvas"
    :viewBox="viewBox"
    :style="{ aspectRatio: aspect }"
    data-testid="layout-lab-canvas"
    @pointerdown="gesture.clear"
  >
    <defs>
      <marker
        id="lab-head"
        viewBox="0 0 10 10"
        refX="10"
        refY="5"
        markerWidth="8"
        markerHeight="8"
        orient="auto-start-reverse"
      >
        <path
          d="M0,0 L10,5 L0,10 z"
          fill="#334155"
        />
      </marker>
    </defs>

    <g
      v-for="shape in shapes"
      :key="shape.alias"
      :class="shape.isBox ? ['lab-box', `lab-box--${shape.kind}`] : 'lab-element'"
      :data-alias="shape.alias"
      @pointerdown="gesture.press($event, shape.alias)"
    >
      <rect
        :x="shape.now.left"
        :y="shape.now.top"
        :width="widthOf(shape.now)"
        :height="heightOf(shape.now)"
        :rx="shape.isBox ? 4 : 3"
      />
      <text
        v-for="(word, index) in shape.words"
        :key="index"
        :x="word.x"
        :y="word.y"
        :textLength="word.width"
        lengthAdjust="spacingAndGlyphs"
        :class="{ 'lab-box__title': shape.isBox }"
      >{{ word.text }}</text>
    </g>

    <g class="lab-lines">
      <polyline
        v-for="{ relation, points } in lines"
        :key="relation.index"
        :points="points"
        :marker-start="relation.decorated[0] ? 'url(#lab-head)' : undefined"
        :marker-end="relation.decorated[1] ? 'url(#lab-head)' : undefined"
      />
      <text
        v-for="{ relation, labelAt } in lines.filter((line) => line.relation.label)"
        :key="`label-${relation.index}`"
        :x="labelAt.x"
        :y="labelAt.y - 4"
        class="lab-lines__label"
      >{{ relation.label }}</text>
    </g>

    <g
      v-if="showBreaches"
      class="lab-breaches"
    >
      <template
        v-for="(mark, index) in marks"
        :key="index"
      >
        <polyline
          v-if="mark.at.length >= 2"
          :points="pointsAttribute(mark.at)"
          :class="`lab-breach lab-breach--${mark.tier}`"
        >
          <title>{{ mark.rule }} ({{ mark.tier }})</title>
        </polyline>
        <template v-else>
          <rect
            v-for="(extent, end) in ends(mark.relation)"
            :key="end"
            :x="extent.left - 3"
            :y="extent.top - 3"
            :width="widthOf(extent) + 6"
            :height="heightOf(extent) + 6"
            :class="`lab-breach-frame lab-breach--${mark.tier}`"
          >
            <title>{{ mark.rule }} ({{ mark.tier }})</title>
          </rect>
        </template>
      </template>
    </g>

    <g
      v-if="selectedExtent"
      class="lab-handles"
    >
      <rect
        :x="selectedExtent.left"
        :y="selectedExtent.top"
        :width="widthOf(selectedExtent)"
        :height="heightOf(selectedExtent)"
        class="lab-handles__frame"
      />
      <rect
        v-for="{ handle, at } in handlesOf(selectedExtent)"
        :key="handle"
        :x="at.x - 4"
        :y="at.y - 4"
        width="8"
        height="8"
        :class="`lab-handles__handle lab-handles__handle--${handle}`"
        :data-handle="handle"
        @pointerdown="gesture.press($event, gesture.selected.value ?? '', handle)"
      />
    </g>
  </svg>
</template>

<style scoped>
.lab-canvas { display: block; width: 100%; height: auto; max-height: 85vh; background: #fff; border: 1px solid #cbd5e1; border-radius: 6px; touch-action: none; user-select: none; }
.lab-box rect { fill: #f8fafc; stroke: #94a3b8; stroke-width: 1; cursor: move; }
.lab-box--domain rect { fill: #f1f5f9; }
.lab-box--authored-grouping rect { fill: #fefce8; stroke-dasharray: 6 3; stroke: #a16207; }
.lab-box--element rect { fill: #ecfeff; stroke: #0e7490; }
.lab-box__title { font-size: 12px; font-weight: 600; fill: #334155; pointer-events: none; }
.lab-element rect { fill: #fffbeb; stroke: #b45309; stroke-width: 1.2; cursor: move; }
.lab-element text { font-size: 12px; fill: #1f2937; pointer-events: none; }
.lab-lines polyline { fill: none; stroke: #334155; stroke-width: 1.3; pointer-events: none; }
.lab-lines__label { font-size: 11px; fill: #475569; text-anchor: middle; pointer-events: none; }
.lab-breach { fill: none; stroke-width: 7; stroke-linecap: round; opacity: 0.45; pointer-events: stroke; }
.lab-breach-frame { fill: none; stroke-width: 3; opacity: 0.7; }
.lab-breach--hard { stroke: #dc2626; }
.lab-breach--soft { stroke: #f59e0b; }
.lab-handles__frame { fill: none; stroke: #2563eb; stroke-dasharray: 4 2; pointer-events: none; }
.lab-handles__handle { fill: #fff; stroke: #2563eb; stroke-width: 1.5; }
.lab-handles__handle--n, .lab-handles__handle--s { cursor: ns-resize; }
.lab-handles__handle--e, .lab-handles__handle--w { cursor: ew-resize; }
.lab-handles__handle--ne, .lab-handles__handle--sw { cursor: nesw-resize; }
.lab-handles__handle--nw, .lab-handles__handle--se { cursor: nwse-resize; }
</style>
