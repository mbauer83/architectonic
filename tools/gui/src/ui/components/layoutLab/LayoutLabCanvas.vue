<script setup lang="ts">
/**
 * The lab's picture: boxes, elements and lines drawn from the real geometry where they are now, with
 * the rule breaches over them and handles on the selected shape. Press and drag a shape to move it; a
 * box carries what it holds. Drag a handle to resize.
 */
import { computed, ref, watch } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import { drawnLine } from '../../../domain/layout/lab/labLineDrawing'
import type { PlacedDrawing } from '../../../domain/layout/lab/labShapeDrawing'
import { shapeDrawing } from '../../../domain/layout/lab/labShapeDrawing'
import type { LayoutLab } from '../../composables/useLayoutLab'
import { dragRegionOf, handlesOf, paintOrder, pointsAttribute } from './labDrawing'
import LabDrawn from './LabDrawn'
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

/** PlantUML's background, stretched from the page it drew over the view the lab shows. */
const backdropTransform = computed((): string => {
  const drawn = geometry.value
  const extent = view.value
  if (!drawn || !extent) return ''
  const { canvas } = drawn
  const across = widthOf(extent) / widthOf(canvas)
  const down = heightOf(extent) / heightOf(canvas)
  return `translate(${extent.left} ${extent.top}) scale(${across} ${down}) translate(${-canvas.left} ${-canvas.top})`
})

interface DrawnShape {
  readonly alias: string
  readonly isBox: boolean
  /** Where it is taken to drag it: the whole outline, a grouping's full-width title band included. */
  readonly region: Extent
  readonly drawing: PlacedDrawing
}

/** Every shape back to front, each where it is now, drawn as PlantUML or the composer drew it. */
const shapes = computed((): DrawnShape[] => {
  const drawn = geometry.value
  const where = placement.value
  if (!drawn || !where) return []
  const known = new Map([...drawn.boxes, ...drawn.elements].map((shape) => [shape.alias, shape]))
  const reshaped = props.lab.reshaped.value
  return paintOrder(drawn, gesture.lifted.value).flatMap(({ alias, isBox }): DrawnShape[] => {
    const shape = known.get(alias)
    const now = isBox ? where.boxes.get(alias) : where.elements.get(alias)
    if (!shape || !now) return []
    const drawing = shapeDrawing(shape.extent, shape.drawing, now, reshaped.get(alias))
    return [{ alias, isBox, region: dragRegionOf(now), drawing }]
  })
})

/** Each line: PlantUML's own until the first change, then drawn along the router's course. */
const lines = computed(() => {
  const drawn = geometry.value
  if (!drawn) return []
  const asDrawn = props.lab.routes.value === null
  return drawn.relations.flatMap((relation) => {
    const course = props.lab.courses.value.get(relation.index)
    if (!course || course.length < 2) return []
    return [{ index: relation.index, asDrawn: asDrawn ? relation.drawing.group : null, along: drawnLine(relation.drawing, course) }]
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
    <LabDrawn
      v-if="geometry"
      class="lab-backdrop"
      :nodes="geometry.backdrop"
      :transform="backdropTransform"
    />

    <g
      v-for="shape in shapes"
      :key="shape.alias"
      :class="shape.isBox ? 'lab-box' : 'lab-element'"
      :data-alias="shape.alias"
      @pointerdown="gesture.press($event, shape.alias)"
    >
      <LabDrawn
        :nodes="[shape.drawing.drawing]"
        :transform="shape.drawing.transform"
      />
      <rect
        class="lab-grip"
        :x="shape.region.left"
        :y="shape.region.top"
        :width="widthOf(shape.region)"
        :height="heightOf(shape.region)"
      />
    </g>

    <g class="lab-lines">
      <template
        v-for="line in lines"
        :key="line.index"
      >
        <LabDrawn
          v-if="line.asDrawn"
          :nodes="[line.asDrawn]"
        />
        <g v-else>
          <LabDrawn :nodes="[line.along.line]" />
          <LabDrawn
            v-for="(end, side) in line.along.ends"
            :key="side"
            :nodes="end.marks"
            :transform="end.transform"
          />
          <LabDrawn
            v-if="line.along.label"
            :nodes="line.along.label.texts"
            :transform="line.along.label.transform"
          />
        </g>
      </template>
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
/* How the picture looks is PlantUML's drawing; only the lab's own marks — grips, breaches, handles — are styled here. */
.lab-canvas { display: block; width: 100%; height: auto; max-height: 85vh; }
.lab-canvas { border: 1px solid #cbd5e1; border-radius: 6px; touch-action: none; user-select: none; }
.lab-backdrop, .lab-lines, .lab-box :deep(g), .lab-element :deep(g) { pointer-events: none; }
.lab-grip { fill: transparent; stroke: none; pointer-events: all; cursor: move; }
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
