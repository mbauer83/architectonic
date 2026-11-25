<script setup lang="ts">
/**
 * The canvas's picture: boxes, elements and lines drawn from the real geometry where they are now, in the
 * one paint order of `labPaintOrder`, with the rule breaches over them and handles on the selected
 * shape. Press and drag a shape to move it; a box carries what it holds. Drag a handle to resize.
 * Press a line, or where it ends on an element's edge, to select it and shape it (`useLineGesture`).
 */
import { computed, ref, watch } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { heightOf, widthOf } from '../../../domain/layout/geometry'
import { useEditingPreferences } from '../../composables/useEditingPreferences'
import type { ArrangementSession } from '../../composables/useArrangementSession'
import type { BreachMark } from './labDrawing'
import { breachMarksOf, pointsAttribute } from './labDrawing'
import { paintOrder } from './labPaintOrder'
import type { DrawnRelation, DrawnShape, Piece } from './labPieces'
import { drawnRelations, drawnShapes, pieceOf } from './labPieces'
import LabDrawn from './LabDrawn'
import CanvasMarks from './CanvasMarks.vue'
import LabBreachMarks from './LabBreachMarks.vue'
import LabSelection from './LabSelection.vue'
import LabLineHandles from './LabLineHandles.vue'
import LabGuides from './LabGuides.vue'
import type { PlacedPart } from '../../composables/useSurroundPlacement'
import { withoutBends } from '../../../domain/layout/lab/labSelection'
import { useCanvasFocus } from './useCanvasFocus'
import { useCanvasView } from './useCanvasView'
import { useLabGesture } from './useLabGesture'
import { useLineGesture } from './useLineGesture'

/** *readonly*: a press picks a shape and nothing moves. The default slot draws over the picture. */
const props = defineProps<{
  session: ArrangementSession; showBreaches?: boolean; readonly?: boolean
  /** The title and the legend, where the page placed them (`useSurroundPlacement`); none, none drawn. */
  surround?: readonly PlacedPart[]
}>()
const emit = defineEmits<{ pick: [alias: string] }>()

const svg = ref<SVGSVGElement | null>(null)
const prefs = useEditingPreferences()
const gesture = useLabGesture(props.session, svg, {
  snapping: () => prefs.snapping.value.value, rectangle: () => prefs.rectangle.value.value,
})
const pick = (event: PointerEvent, alias: string) => { gesture.select(event, alias); emit('pick', alias) }
const focus = useCanvasFocus(props.session, gesture)

const geometry = computed(() => props.session.geometry.value)
const placement = computed(() => props.session.placement.value)
/** Where the bends the selection holds are, which the selection marks. */
const selectedBends = computed(() => gesture.bends.value.flatMap(({ key, index }) => {
  const at = props.session.arrangement.value?.routes.get(key)?.via?.[index]
  return at ? [{ x: at[0], y: at[1] }] : []
}))
const { viewBox, pixel, aspect, backdropTransform } = useCanvasView(
  props.session, svg, gesture.dragging, () => (props.surround ?? []).map((part) => part.extent))

/** A handle is the same size on screen however far the picture is zoomed out to fit. */
const HANDLE_PIXELS = 9
const handleSide = computed((): number => HANDLE_PIXELS * pixel.value)

/** A line selected is the selection: picking one lets go of the shapes, and picking a shape the line. */
const lineGesture = useLineGesture(props.session, svg, pixel, () => gesture.clear())
watch(() => gesture.selection.value, (now) => { if (now.length > 0) lineGesture.clear() })
// A restacking is explicit: the shape last dropped is no longer lifted over what it was stacked behind.
watch(() => props.session.arrangement.value?.z, () => { gesture.lifted.value = null })
const pressShape = (event: PointerEvent, alias: string) => {
  focus.pointed(alias)
  if (!lineGesture.pressNearAnEnd(event)) gesture.press(event, alias)
}
const sweep = (event: PointerEvent) => {
  if (event.button === 0) { lineGesture.clear(); focus.pointed(null) }
  gesture.sweepFrom(event)
}
const selectedLine = computed(() => {
  const routed = lineGesture.routed.value
  return lineGesture.line.value === null || !routed ? null : { line: lineGesture.line.value, course: routed.course }
})

defineExpose({
  /** Whether anything is selected or focused; and clearing both, as Escape's first step does. */
  hasSelection: computed(() =>
    gesture.selection.value.length > 0 || gesture.bends.value.length > 0 || lineGesture.line.value !== null
    || focus.focused.value !== null),
  /** The one shape selected, or null when none or several are; and every shape selected. */
  selected: gesture.selected,
  selection: gesture.selection,
  /** The bends a selection rectangle picked up (sketch 02·8); and removing them, as Delete does. */
  selectedBends: gesture.bends,
  removeSelectedBends: (): boolean => {
    const picked = gesture.bends.value
    if (picked.length === 0) return false
    props.session.change((_drawn, now) => withoutBends(now, picked))
    gesture.bends.value = []
    return true
  },
  /** The line selected, by its place on the picture; null when none is. */
  selectedLine: lineGesture.line,
  clearSelection: () => { gesture.clear(); lineGesture.clear(); focus.clear() },
  /** The element focus the keys move (`useCanvasFocus`): where it is, as announced; and the arrows on a label. */
  focus: { step: focus.step, enter: focus.enter, towards: focus.towards, selectAll: focus.selectAll },
  focusedExtent: focus.extent,
  announced: focus.announced,
  nudgeLabel: lineGesture.nudgeLabel,
  /** Delete on a picked bend removes it, as one step; answers whether there was one. */
  removePickedBend: () => lineGesture.removePickedBend(),
  /** Begin a selection rectangle from a press beside the picture, on the page's empty paper: not a control. */
  sweepFrom: (event: PointerEvent) => {
    if (!(event.target instanceof Element && event.target.closest('button, a, input, select, textarea'))) {
      sweep(event)
    }
  },
})

/** Every shape and line where it is now, drawn as PlantUML or the composer drew it (`labPieces`). */
const shapes = computed((): ReadonlyMap<string, DrawnShape> => {
  const drawn = geometry.value
  const where = placement.value
  return drawn && where ? drawnShapes(drawn, where, props.session.reshaped.value) : new Map()
})
const lines = computed((): ReadonlyMap<number, DrawnRelation> => {
  const drawn = geometry.value
  const anchors = new Map([...props.session.arrangement.value?.routes ?? []]
    .flatMap(([key, route]) => (route.label ? [[key, route.label] as const] : [])))
  return drawn ? drawnRelations(drawn, props.session.courses.value, props.session.routes.value === null, anchors)
    : new Map()
})

/** The picture back to front (`labPaintOrder`): shapes by nesting, then lines, then labels. */
const pieces = computed((): Piece[] => {
  const drawn = geometry.value
  const where = placement.value
  return drawn && where ? paintOrder(drawn, where, gesture.lifted.value, props.session.arrangement.value?.z)
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
  (props.showBreaches ? breachMarksOf(props.session.breaches.value, ends) : []))

/** The shapes back to front, as painted: what the marks read what covers what from. */
const shapeOrder = computed(() => pieces.value.flatMap((piece) => (piece.kind === 'shape' ? [piece.shape.alias] : [])))

</script>

<template>
  <svg
    ref="svg"
    class="lab-canvas"
    :viewBox="viewBox"
    :style="{ aspectRatio: aspect }"
    data-testid="layout-lab-canvas"
    @pointerdown="readonly ? gesture.clear() : sweep($event)"
  >
    <!-- The picture itself, without the marks and handles drawn over it: what the overview shows. -->
    <g data-picture-drawing>
      <LabDrawn
        v-if="geometry"
        class="lab-backdrop"
        :nodes="geometry.backdrop"
        :transform="backdropTransform"
      />
      <LabDrawn
        v-for="(around, index) in surround ?? []"
        :key="`surround-${index}`"
        class="lab-surround"
        data-testid="canvas-surround"
        :nodes="[around.part.drawing]"
        :transform="`translate(${around.by.x} ${around.by.y})`"
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
          @pointerdown="readonly ? pick($event, piece.shape.alias) : pressShape($event, piece.shape.alias)"
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
            @pointerdown="readonly ? pick($event, piece.shape.alias) : gesture.sweepFrom($event, piece.shape.alias)"
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
          <polyline
            v-if="!readonly"
            class="lab-line-hit"
            :points="pointsAttribute(session.courses.value.get(piece.relation) ?? [])"
            @pointerdown="lineGesture.pressLine($event, piece.relation)"
          />
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
          :class="['lab-line-label', { 'lab-line-label--movable': !readonly }]"
          :data-relation="piece.relation"
          data-painted="label"
          @pointerdown="readonly || lineGesture.pressLabel($event, piece.relation)"
        >
          <LabDrawn
            :nodes="piece.label.texts"
            :transform="piece.label.transform"
          />
        </g>
      </template>
    </g>

    <LabBreachMarks
      v-if="showBreaches"
      :marks="marks"
      :geometry="geometry"
    />

    <CanvasMarks
      :session="session"
      :order="shapeOrder"
    />

    <slot />

    <LabGuides :guides="[...gesture.guides.value, ...lineGesture.guides.value]" />

    <LabSelection
      :placement="placement"
      :selection="gesture.selection.value"
      :rectangle="gesture.rectangle.value"
      :rule="prefs.rectangle.value.value"
      :ring="focus.ring.value"
      :bends="selectedBends"
      :pixel="pixel"
      :handle-side="handleSide"
      :readonly="readonly"
      @handle="(event, handle) => gesture.press(event, gesture.selected.value ?? '', handle)"
    />

    <LabLineHandles
      v-if="!readonly && selectedLine"
      :line="selectedLine.line"
      :course="selectedLine.course"
      :bends="lineGesture.bends.value"
      :picked="lineGesture.bend.value"
      :anchor="lineGesture.stated.value.label ?? null"
      :leader="lineGesture.movingLabel.value"
      :handle-side="handleSide"
      @end="lineGesture.pressEnd"
      @segment="lineGesture.pressSegment"
      @bend="lineGesture.pressBend"
      @remove-bend="lineGesture.doublePress"
      @add-bend="lineGesture.doublePress"
    />
  </svg>
</template>

<style scoped>
/* How the picture looks is PlantUML's drawing; only the canvas's own marks — grips, breaches, handles —
   are styled here. */
.lab-canvas { display: block; width: 100%; height: auto; max-height: 85vh; }
/* The picture is the canvas: no frame of its own, which is the page's to draw for its mode. */
.lab-canvas { touch-action: none; user-select: none; }
.lab-backdrop, .lab-surround, .lab-line, .lab-line-label, .lab-box :deep(g), .lab-element :deep(g) {
  pointer-events: none;
}
/* A line is pressed along a band wider than its stroke; a label is moved by its text. */
.lab-line-hit { fill: none; stroke: transparent; stroke-width: 10px; pointer-events: stroke; cursor: pointer; }
.lab-line-hit { vector-effect: non-scaling-stroke; }
.lab-line-label--movable { pointer-events: bounding-box; cursor: move; }
.lab-grip { fill: transparent; stroke: none; pointer-events: all; cursor: move; }
/* A box moves by its title band, which shows its whole width under the pointer; its body selects. */
.lab-box > .lab-grip:hover { fill: var(--paper-accent-hover); }
.lab-body { fill: transparent; stroke: none; pointer-events: all; cursor: default; }
/* While a shape is dragged, it is drawn see-through, so what it is passing over — and the lines into
   what it covers — stay in sight until it is dropped. */
.lab-carried { opacity: 0.55; }
</style>
