/**
 * The canvas's pointer gesture: press a shape and drag it to move it — an element anywhere, a box by its
 * title band — or press one of its handles and drag to resize it. A press without travel only selects.
 *
 * Several shapes can be selected (sketch 02·8). Shift-click toggles one (Ctrl too; Cmd on Apple:
 * `isAdditive`); pressing a selected shape drags the whole selection; a rectangle swept from empty
 * paper or from a box's body selects what it chooses (`chosenBy`), and with Shift adds it. A press on
 * a box's body that does not travel selects the box.
 *
 * A drag begins a step of the session first, and only then reads where things are: on a picture still
 * arranged automatically, beginning takes it over (`useArrangementSession`), which may move shapes, and
 * the drag continues from where the takeover put them. Each frame states the arrangement the drag has
 * reached and which shapes it moved; the release commits it.
 */
import { computed, ref } from 'vue'
import type { Ref } from 'vue'
import type { Extent, Point } from '../../../domain/layout/geometry'
import { distanceBetween, extentAround } from '../../../domain/layout/geometry'
import type { Arrangement, Handle } from '../../../domain/layout/lab/labArrangement'
import { SMALLEST_ELEMENT, movedTogether, resized, resizedExtent } from '../../../domain/layout/lab/labArrangement'
import { changedShapes, placementOf } from '../../../domain/layout/lab/labRouting'
import type { Placement } from '../../../domain/layout/lab/labRouting'
import { chosenBy, toggled } from '../../../domain/layout/lab/labSelection'
import type { ArrangementSession } from '../../composables/useArrangementSession'
import { isAdditive } from '../../lib/additiveClick'
import type { Lift } from './labPaintOrder'

/** How far a press travels before it is a drag rather than a click. */
const TRAVEL = 4

interface Pressed {
  /** The shape pressed, and every shape the drag moves with it. */
  readonly alias: string
  readonly moving: readonly string[]
  readonly handle: Handle | null
  readonly from: Point
  /** Where the drag starts from: read once the step has begun. */
  start: { readonly arrangement: Arrangement; readonly placement: Placement; readonly extent: Extent } | null
}

interface Sweep {
  /** The box whose body the sweep began on, which a press without travel selects; null on empty paper. */
  readonly box: string | null
  readonly additive: boolean
  readonly before: readonly string[]
  readonly from: Point
}

export function useLabGesture(session: ArrangementSession, svg: Ref<SVGSVGElement | null>) {
  /** Every shape selected, in the order chosen. */
  const selection = ref<readonly string[]>([])
  /** The one shape selected, or null when none or several are. */
  const selected = computed(() => (selection.value.length === 1 ? selection.value[0] : null))
  /** The selection rectangle being swept, until it is released. */
  const rectangle = ref<Extent | null>(null)
  /** The shape last pressed and how, which the paint order brings forward (`labPaintOrder`). */
  const lifted = ref<Lift | null>(null)
  /** Whether a press has travelled far enough to be a drag, until it is released. */
  const dragging = ref(false)
  let pressed: Pressed | null = null
  let sweep: Sweep | null = null

  const pointIn = (event: PointerEvent): Point => {
    const matrix = svg.value?.getScreenCTM()
    if (!matrix) return { x: event.clientX, y: event.clientY }
    const inverse = matrix.inverse()
    return {
      x: inverse.a * event.clientX + inverse.c * event.clientY + inverse.e,
      y: inverse.b * event.clientX + inverse.d * event.clientY + inverse.f,
    }
  }

  // Followed on the window, not by pointer capture: pressing a shape paints it in front, which moves
  // its node, and a moved node loses its capture — the release then landed nowhere.
  const follow = (on: boolean) => {
    for (const [type, listener] of [['pointermove', drag], ['pointerup', release], ['pointercancel', release]] as const) {
      if (on) window.addEventListener(type, listener)
      else window.removeEventListener(type, listener)
    }
  }

  /** Select *alias* alone, without moving it: a press on a shape of a picture that is only read. */
  const select = (event: PointerEvent, alias: string) => {
    if (event.button !== 0) return
    event.stopPropagation()
    selection.value = [alias]
  }

  const press = (event: PointerEvent, alias: string, handle: Handle | null = null) => {
    const placement = session.placement.value
    if (!placement || !(placement.elements.has(alias) || placement.boxes.has(alias)) || event.button !== 0) return
    event.stopPropagation()
    if (handle === null && isAdditive(event)) {
      selection.value = toggled(selection.value, alias)
      return
    }
    const together = handle === null && selection.value.includes(alias)
    if (!together) selection.value = [alias]
    follow(true)
    lifted.value = { alias, how: handle === null ? 'moved' : 'resized' }
    pressed = { alias, moving: together ? selection.value : [alias], handle, from: pointIn(event), start: null }
  }

  /** Begin a selection rectangle: on empty paper (*box* null), or on a box's body. */
  const sweepFrom = (event: PointerEvent, box: string | null = null) => {
    if (event.button !== 0) return
    event.stopPropagation()
    follow(true)
    sweep = { box, additive: isAdditive(event), before: selection.value, from: pointIn(event) }
  }

  /** Begin the step, then read where the drag starts from. */
  const started = (state: Pressed): Pressed['start'] => {
    session.begin()
    const arrangement = session.arrangement.value
    const placement = session.placement.value
    const extent = placement?.elements.get(state.alias) ?? placement?.boxes.get(state.alias)
    return arrangement && placement && extent ? { arrangement, placement, extent } : null
  }

  const reached = (state: Pressed, dx: number, dy: number): Arrangement | null => {
    const geometry = session.geometry.value
    const start = state.start
    if (!geometry || !start) return null
    if (state.handle === null) return movedTogether(geometry, start.arrangement, state.moving, dx, dy)
    const least = geometry.boxes.some((box) => box.alias === state.alias) ? 1 : SMALLEST_ELEMENT
    return resized(geometry, start.arrangement, state.alias, resizedExtent(start.extent, state.handle, dx, dy, least))
  }

  const swept = (state: Sweep, at: Point) => {
    const placement = session.placement.value
    const travelled = distanceBetween(state.from, at) >= TRAVEL
    const spanned = extentAround([state.from, at])
    if (!placement || !spanned || (!travelled && rectangle.value === null)) return
    rectangle.value = spanned
    const chosen = chosenBy(spanned, placement)
    selection.value = state.additive ? [...new Set([...state.before, ...chosen])] : chosen
  }

  const drag = (event: PointerEvent) => {
    if (sweep) return swept(sweep, pointIn(event))
    const state = pressed
    const geometry = session.geometry.value
    if (!state || !geometry) return
    const at = pointIn(event)
    const dx = Math.round(at.x - state.from.x)
    const dy = Math.round(at.y - state.from.y)
    if (!state.start) {
      if (Math.hypot(dx, dy) < TRAVEL) return
      state.start = started(state)
      dragging.value = true
    }
    const next = reached(state, dx, dy)
    if (next && state.start) session.preview(next, changedShapes(state.start.placement, placementOf(geometry, next)))
  }

  /** A sweep that never travelled is a click: on a box's body it selects the box, on paper it clears. */
  const clicked = (state: Sweep) => {
    if (state.box) selection.value = state.additive ? toggled(state.before, state.box) : [state.box]
    else if (!state.additive) selection.value = []
  }

  const release = () => {
    follow(false)
    if (sweep && rectangle.value === null) clicked(sweep)
    if (pressed?.start) session.commit()
    pressed = null
    sweep = null
    rectangle.value = null
    dragging.value = false
  }

  const clear = () => { selection.value = [] }

  return { selection, selected, rectangle, lifted, dragging, press, select, sweepFrom, drag, release, clear }
}
