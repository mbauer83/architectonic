<script setup lang="ts">
/**
 * The lab's picture: boxes, elements and lines drawn from the real geometry where they are now, in the
 * one paint order of `labPaintOrder`, with the rule breaches over them and handles on the selected
 * shape. Press and drag a shape to move it; a box carries what it holds. Drag a handle to resize.
 */
import { computed, ref, watch } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import type { DrawingNode } from '../../../domain/layout/lab/labGeometry'
import type { DrawnLine } from '../../../domain/layout/lab/labLineDrawing'
import { drawnLine } from '../../../domain/layout/lab/labLineDrawing'
import type { PlacedDrawing } from '../../../domain/layout/lab/labShapeDrawing'
import { shapeDrawing } from '../../../domain/layout/lab/labShapeDrawing'
import { useElementSize } from '../../composables/useElementSize'
import type { LayoutLab } from '../../composables/useLayoutLab'
import type { BreachMark } from './labDrawing'
import { breachMarksOf, dragRegionOf, handlesOf, pointsAttribute } from './labDrawing'
import type { Painted } from './labPaintOrder'
import { paintOrder } from './labPaintOrder'
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

/** How wide the picture is shown on screen, in pixels: what a handle's size on screen is reckoned from. */
const { width: shownWidth } = useElementSize(() => svg.value)

/** One pixel on screen, in the picture's units: what the lab's own marks are sized by. */
const pixel = computed((): number => {
  const extent = view.value
  return extent && shownWidth.value > 0 ? widthOf(extent) / shownWidth.value : 1
})

/** A handle, and a breach's tag, are the same size on screen however far the picture is zoomed out to fit. */
const HANDLE_PIXELS = 9
const TAG_PIXELS = 11
const handleSide = computed((): number => HANDLE_PIXELS * pixel.value)
const tagSize = computed((): number => TAG_PIXELS * pixel.value)

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

/** Every shape, by alias, where it is now, drawn as PlantUML or the composer drew it. */
const shapes = computed((): ReadonlyMap<string, DrawnShape> => {
  const drawn = geometry.value
  const where = placement.value
  if (!drawn || !where) return new Map()
  const reshaped = props.lab.reshaped.value
  const all = [...drawn.boxes.map((shape) => ({ shape, isBox: true })), ...drawn.elements.map((shape) => ({ shape, isBox: false }))]
  return new Map(all.flatMap(({ shape, isBox }): [string, DrawnShape][] => {
    const now = isBox ? where.boxes.get(shape.alias) : where.elements.get(shape.alias)
    if (!now) return []
    const drawing = shapeDrawing(shape.extent, shape.drawing, now, reshaped.get(shape.alias))
    return [[shape.alias, { alias: shape.alias, isBox, region: dragRegionOf(now), drawing }]]
  }))
})

interface DrawnRelation {
  /** PlantUML's own drawing of the whole relation, label and decorations in it, until the first change. */
  readonly asDrawn: DrawingNode | null
  readonly along: DrawnLine
}

/** Each line, by its place: PlantUML's own until the first change, then drawn along the router's course. */
const lines = computed((): ReadonlyMap<number, DrawnRelation> => {
  const drawn = geometry.value
  if (!drawn) return new Map()
  const asDrawn = props.lab.routes.value === null
  return new Map(drawn.relations.flatMap((relation): [number, DrawnRelation][] => {
    const course = props.lab.courses.value.get(relation.index)
    if (!course || course.length < 2) return []
    const along = drawnLine(relation.drawing, course)
    return [[relation.index, { asDrawn: asDrawn ? relation.drawing.group : null, along }]]
  }))
})

/** One piece of the picture, ready to draw. */
type Piece =
  | { readonly kind: 'shape'; readonly key: string; readonly shape: DrawnShape }
  | { readonly kind: 'line'; readonly key: string; readonly relation: number; readonly drawn: DrawnRelation }
  | {
    readonly kind: 'label'; readonly key: string; readonly relation: number
    readonly label: NonNullable<DrawnLine['label']>
  }

/** What *painted* draws, if anything: a label drawn inside PlantUML's own relation has no piece of its own. */
const pieceOf = (painted: Painted): Piece[] => {
  if (painted.kind === 'shape') {
    const shape = shapes.value.get(painted.alias)
    return shape ? [{ kind: 'shape', key: `shape:${painted.alias}`, shape }] : []
  }
  const drawn = lines.value.get(painted.relation)
  if (!drawn) return []
  if (painted.kind === 'line') return [{ kind: 'line', key: `line:${painted.relation}`, relation: painted.relation, drawn }]
  const label = drawn.asDrawn === null ? drawn.along.label : null
  return label ? [{ kind: 'label', key: `label:${painted.relation}`, relation: painted.relation, label }] : []
}

/** The picture back to front (`labPaintOrder`): shapes by nesting, then lines, then labels. */
const pieces = computed((): Piece[] => {
  const drawn = geometry.value
  const where = placement.value
  return drawn && where ? paintOrder(drawn, where, gesture.lifted.value).flatMap(pieceOf) : []
})

const ends = (relationIndex: number): Extent[] => {
  const relation = geometry.value?.relations.find((one) => one.index === relationIndex)
  const where = placement.value
  if (!relation || !where) return []
  return [relation.source, relation.target].flatMap((alias) => {
    const extent = where.elements.get(alias) ?? where.boxes.get(alias)
    return extent ? [extent] : []
  })
}

const marks = computed((): BreachMark[] =>
  (props.showBreaches ? breachMarksOf(props.lab.breaches.value, ends, tagSize.value) : []))

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

    <template
      v-for="piece in pieces"
      :key="piece.key"
    >
      <g
        v-if="piece.kind === 'shape'"
        :class="piece.shape.isBox ? 'lab-box' : 'lab-element'"
        :data-alias="piece.shape.alias"
        data-painted="shape"
        @pointerdown="gesture.press($event, piece.shape.alias)"
      >
        <LabDrawn
          :nodes="[piece.shape.drawing.drawing]"
          :transform="piece.shape.drawing.transform"
        />
        <rect
          class="lab-grip"
          :x="piece.shape.region.left"
          :y="piece.shape.region.top"
          :width="widthOf(piece.shape.region)"
          :height="heightOf(piece.shape.region)"
        />
      </g>
      <g
        v-else-if="piece.kind === 'line'"
        class="lab-line"
        :data-relation="piece.relation"
        data-painted="line"
      >
        <LabDrawn
          v-if="piece.drawn.asDrawn"
          :nodes="[piece.drawn.asDrawn]"
        />
        <template v-else>
          <LabDrawn :nodes="[piece.drawn.along.line]" />
          <LabDrawn
            v-for="(end, side) in piece.drawn.along.ends"
            :key="side"
            :nodes="end.marks"
            :transform="end.transform"
          />
        </template>
      </g>
      <g
        v-else
        class="lab-line-label"
        :data-relation="piece.relation"
        data-painted="label"
      >
        <LabDrawn
          :nodes="piece.label.texts"
          :transform="piece.label.transform"
        />
      </g>
    </template>

    <g
      v-if="showBreaches"
      class="lab-breaches"
    >
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
          class="lab-breach"
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
        <text
          v-if="mark.tagAt"
          class="lab-breach-tag"
          :x="mark.tagAt.x"
          :y="mark.tagAt.y"
          :font-size="tagSize"
          :stroke-width="tagSize / 4"
        >{{ mark.tag }}</text>
      </g>
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
        :x="at.x - handleSide / 2"
        :y="at.y - handleSide / 2"
        :width="handleSide"
        :height="handleSide"
        :class="`lab-handles__handle lab-handles__handle--${handle}`"
        :data-handle="handle"
        @pointerdown="gesture.press($event, gesture.selected.value ?? '', handle)"
      />
    </g>
  </svg>
</template>

<style scoped>
/* How the picture looks is PlantUML's drawing; only the lab's own marks — grips, breaches, handles —
   are styled here. */
.lab-canvas { display: block; width: 100%; height: auto; max-height: 85vh; }
/* Always being edited, so framed as a canvas in edit mode is. */
.lab-canvas { border: 2px solid var(--accent); border-radius: 6px; touch-action: none; user-select: none; }
.lab-backdrop, .lab-line, .lab-line-label, .lab-box :deep(g), .lab-element :deep(g) { pointer-events: none; }
.lab-grip { fill: transparent; stroke: none; pointer-events: all; cursor: move; }
/* A breach is marked in its tier's colour along exactly the stretch that breaks the rule — square
   ends, so the mark stops where the stretch does and never spills round a bend — and tagged with the
   rule's name. */
.lab-breach-mark { --breach: #dc2626; }
.lab-breach-mark.lab-breach--soft { --breach: #d97706; }
.lab-breach { fill: none; stroke: var(--breach); stroke-width: 6px; stroke-linecap: butt; opacity: 0.4; }
.lab-breach, .lab-breach-frame { vector-effect: non-scaling-stroke; pointer-events: stroke; }
.lab-breach-frame { fill: none; stroke: var(--breach); stroke-width: 2px; stroke-dasharray: 5 3; opacity: 0.8; }
.lab-breach-tag {
  fill: var(--breach); stroke: #fff; paint-order: stroke; stroke-linejoin: round; text-anchor: middle;
  font-family: system-ui, sans-serif; font-weight: 600; pointer-events: none;
}
.lab-handles__frame { fill: none; stroke: var(--accent); stroke-width: 1.5px; pointer-events: none; }
.lab-handles__frame, .lab-handles__handle { vector-effect: non-scaling-stroke; }
.lab-handles__handle { fill: #fff; stroke: var(--accent); stroke-width: 1.5px; }
.lab-handles__handle--n, .lab-handles__handle--s { cursor: ns-resize; }
.lab-handles__handle--e, .lab-handles__handle--w { cursor: ew-resize; }
.lab-handles__handle--ne, .lab-handles__handle--sw { cursor: nesw-resize; }
.lab-handles__handle--nw, .lab-handles__handle--se { cursor: nwse-resize; }
</style>
