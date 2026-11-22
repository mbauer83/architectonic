<script setup lang="ts">
/**
 * The lab's picture: boxes, elements and lines drawn from the real geometry where they are now, in the
 * one paint order of `labPaintOrder`, with the rule breaches over them and handles on the selected
 * shape. Press and drag a shape to move it; a box carries what it holds. Drag a handle to resize.
 */
import { computed, ref, watch } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import { useElementSize } from '../../composables/useElementSize'
import type { ArrangementSession } from '../../composables/useArrangementSession'
import type { BreachMark } from './labDrawing'
import { breachMarksOf, handlesOf, pointsAttribute } from './labDrawing'
import { paintOrder } from './labPaintOrder'
import type { DrawnRelation, DrawnShape, Piece } from './labPieces'
import { drawnRelations, drawnShapes, pieceOf } from './labPieces'
import LabDrawn from './LabDrawn'
import { useLabGesture } from './useLabGesture'

const props = defineProps<{ session: ArrangementSession; showBreaches?: boolean }>()

const svg = ref<SVGSVGElement | null>(null)
const gesture = useLabGesture(props.session, svg)

/** Room round the drawing, so a shape dragged out of it stays in reach. */
const MARGIN = 40

const geometry = computed(() => props.session.geometry.value)
const placement = computed(() => props.session.placement.value)

/** What is drawn now, shapes and lines: the view fits it, not PlantUML's page with its title. */
const drawnExtent = computed((): Extent | null => {
  const where = placement.value
  if (!where) return null
  const points = [...props.session.courses.value.values()].flat()
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

const union = (one: Extent, other: Extent): Extent => ({
  left: Math.min(one.left, other.left), top: Math.min(one.top, other.top),
  right: Math.max(one.right, other.right), bottom: Math.max(one.bottom, other.bottom),
})

/**
 * The view: PlantUML's page, grown to take in whatever is drawn beyond it and never shrunk, so the
 * picture keeps its scale while it is arranged. Held still while something is dragged, so the point
 * under the pointer keeps meaning the same place on the picture.
 */
const view = ref<Extent | null>(null)
const grown = (now: Extent | null): Extent | null => {
  const page = geometry.value?.canvas ?? null
  const before = view.value ?? page
  return now && before ? union(before, now) : (now ?? before)
}
watch(geometry, () => { view.value = null })
watch(drawnExtent, (now) => { if (!gesture.dragging.value || !view.value) view.value = grown(now) }, { immediate: true })
watch(() => gesture.dragging.value, (dragging) => { if (!dragging) view.value = grown(drawnExtent.value) })

defineExpose({
  /** Whether a shape is selected; and clearing it, as Escape's first step does. */
  hasSelection: computed(() => gesture.selected.value !== null),
  clearSelection: () => gesture.clear(),
})

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

/** Every shape and line where it is now, drawn as PlantUML or the composer drew it (`labPieces`). */
const shapes = computed((): ReadonlyMap<string, DrawnShape> => {
  const drawn = geometry.value
  const where = placement.value
  return drawn && where ? drawnShapes(drawn, where, props.session.reshaped.value) : new Map()
})
const lines = computed((): ReadonlyMap<number, DrawnRelation> => {
  const drawn = geometry.value
  return drawn ? drawnRelations(drawn, props.session.courses.value, props.session.routes.value === null) : new Map()
})

/** The picture back to front (`labPaintOrder`): shapes by nesting, then lines, then labels. */
const pieces = computed((): Piece[] => {
  const drawn = geometry.value
  const where = placement.value
  return drawn && where ? paintOrder(drawn, where, gesture.lifted.value)
    .flatMap((painted) => pieceOf(painted, shapes.value, lines.value)) : []
})

/**
 * The shape being dragged to move it, drawn see-through until it is dropped so the user sees what it
 * covers; null when nothing is. Only the shape pressed — what it holds is drawn as ever — and not one
 * being resized, which is painted under the siblings it grows over and so covers nothing.
 */
const carried = computed((): string | null => {
  const lift = gesture.lifted.value
  return gesture.dragging.value && lift?.how === 'moved' ? lift.alias : null
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
  (props.showBreaches ? breachMarksOf(props.session.breaches.value, ends, tagSize.value) : []))

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
        :class="[piece.shape.isBox ? 'lab-box' : 'lab-element', { 'lab-carried': piece.shape.alias === carried }]"
        :data-alias="piece.shape.alias"
        data-painted="shape"
        @pointerdown="gesture.press($event, piece.shape.alias)"
      >
        <LabDrawn
          :nodes="[piece.shape.drawing.drawing]"
          :transform="piece.shape.drawing.transform"
        />
        <rect
          v-if="piece.shape.body"
          class="lab-body"
          :x="piece.shape.body.left"
          :y="piece.shape.body.top"
          :width="widthOf(piece.shape.body)"
          :height="heightOf(piece.shape.body)"
          @pointerdown="gesture.select($event, piece.shape.alias)"
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
          >{{ mark.tag }}</text>
        </template>
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
/* The picture is the canvas: no frame of its own, which is the page's to draw for its mode. */
.lab-canvas { touch-action: none; user-select: none; }
.lab-backdrop, .lab-line, .lab-line-label, .lab-box :deep(g), .lab-element :deep(g) { pointer-events: none; }
.lab-grip { fill: transparent; stroke: none; pointer-events: all; cursor: move; }
/* A box moves by its title band, which shows its whole width under the pointer; its body selects. */
.lab-box > .lab-grip:hover { fill: rgba(37, 99, 235, 0.09); }
.lab-body { fill: transparent; stroke: none; pointer-events: all; cursor: default; }
/* While a shape is dragged, it is drawn see-through, so what it is passing over — and the lines into
   what it covers — stay in sight until it is dropped. */
.lab-carried { opacity: 0.55; }
/* A breach is an annotation, never line styling: a pale halo far wider than any line round the
   stretch that breaks the rule, or a dashed frame round each end, and the rule's name in a tag of its
   own set off the line, with a dotted leader back to it. */
.lab-breach-mark { --breach: #dc2626; }
.lab-breach-mark.lab-breach--soft { --breach: #d97706; }
.lab-breach-halo {
  fill: none; stroke: var(--breach); stroke-width: 16px; stroke-linecap: round; stroke-linejoin: round; opacity: 0.16;
}
.lab-breach-halo, .lab-breach-frame, .lab-breach-leader, .lab-breach-tag-box { vector-effect: non-scaling-stroke; }
.lab-breach-halo, .lab-breach-frame { pointer-events: stroke; }
.lab-breach-frame { fill: none; stroke: var(--breach); stroke-width: 2px; stroke-dasharray: 5 3; opacity: 0.8; }
.lab-breach-leader { stroke: var(--breach); stroke-width: 1px; stroke-dasharray: 1 2; pointer-events: none; }
.lab-breach-tag-box { fill: #fff; stroke: var(--breach); stroke-width: 1px; pointer-events: none; }
.lab-breach-tag {
  fill: var(--breach); text-anchor: middle; font-family: system-ui, sans-serif; font-weight: 600; pointer-events: none;
}
.lab-handles__frame { fill: none; stroke: var(--accent); stroke-width: 1.5px; pointer-events: none; }
.lab-handles__frame, .lab-handles__handle { vector-effect: non-scaling-stroke; }
.lab-handles__handle { fill: #fff; stroke: var(--accent); stroke-width: 1.5px; }
.lab-handles__handle--n, .lab-handles__handle--s { cursor: ns-resize; }
.lab-handles__handle--e, .lab-handles__handle--w { cursor: ew-resize; }
.lab-handles__handle--ne, .lab-handles__handle--sw { cursor: nesw-resize; }
.lab-handles__handle--nw, .lab-handles__handle--se { cursor: nwse-resize; }
</style>
