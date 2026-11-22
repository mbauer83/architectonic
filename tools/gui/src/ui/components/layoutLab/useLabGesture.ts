/**
 * The canvas's pointer gesture: press a shape and drag it to move it — an element anywhere, a box by its
 * title band — or press one of its handles and drag to resize it. A press without travel only selects,
 * as a press on a box's body does. Each frame states the arrangement the drag has reached and which
 * shapes it moved; the release commits it.
 *
 * The drag begins a step of the session first, and only then reads where things are: on a picture
 * still arranged automatically, beginning takes it over (`useArrangementSession`), which may move
 * shapes, and the drag continues from where the takeover put them.
 */
import { ref } from 'vue'
import type { Ref } from 'vue'
import type { Extent, Point } from '../../../domain/layout/geometry'
import type { Arrangement, Handle } from '../../../domain/layout/lab/labArrangement'
import { SMALLEST_ELEMENT, moved, resized, resizedExtent } from '../../../domain/layout/lab/labArrangement'
import { changedShapes, placementOf } from '../../../domain/layout/lab/labRouting'
import type { Placement } from '../../../domain/layout/lab/labRouting'
import type { ArrangementSession } from '../../composables/useArrangementSession'
import type { Lift } from './labPaintOrder'

/** How far a press travels before it is a drag rather than a click. */
const TRAVEL = 4

interface Pressed {
  readonly alias: string
  readonly handle: Handle | null
  readonly from: Point
  /** Where the drag starts from: read once the step has begun. */
  start: { readonly arrangement: Arrangement; readonly placement: Placement; readonly extent: Extent } | null
}

export function useLabGesture(session: ArrangementSession, svg: Ref<SVGSVGElement | null>) {
  const selected = ref<string | null>(null)
  /** The shape last pressed and how, which the paint order brings forward (`labPaintOrder`). */
  const lifted = ref<Lift | null>(null)
  /** Whether a press has travelled far enough to be a drag, until it is released. */
  const dragging = ref(false)
  let pressed: Pressed | null = null

  const pointIn = (event: PointerEvent): Point => {
    const matrix = svg.value?.getScreenCTM()
    if (!matrix) return { x: event.clientX, y: event.clientY }
    const inverse = matrix.inverse()
    return {
      x: inverse.a * event.clientX + inverse.c * event.clientY + inverse.e,
      y: inverse.b * event.clientX + inverse.d * event.clientY + inverse.f,
    }
  }

  /** Select *alias* without moving it: a press on a box's body. */
  const select = (event: PointerEvent, alias: string) => {
    if (event.button !== 0) return
    event.stopPropagation()
    selected.value = alias
  }

  const press = (event: PointerEvent, alias: string, handle: Handle | null = null) => {
    const placement = session.placement.value
    if (!placement || !(placement.elements.has(alias) || placement.boxes.has(alias)) || event.button !== 0) return
    event.stopPropagation()
    // Followed on the window, not by pointer capture: pressing a shape paints it in front, which moves
    // its node, and a moved node loses its capture — the release then landed nowhere.
    window.addEventListener('pointermove', drag)
    window.addEventListener('pointerup', release)
    window.addEventListener('pointercancel', release)
    selected.value = alias
    lifted.value = { alias, how: handle === null ? 'moved' : 'resized' }
    pressed = { alias, handle, from: pointIn(event), start: null }
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
    if (state.handle === null) return moved(geometry, start.arrangement, state.alias, dx, dy)
    const least = geometry.boxes.some((box) => box.alias === state.alias) ? 1 : SMALLEST_ELEMENT
    return resized(geometry, start.arrangement, state.alias, resizedExtent(start.extent, state.handle, dx, dy, least))
  }

  const drag = (event: PointerEvent) => {
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

  const release = () => {
    window.removeEventListener('pointermove', drag)
    window.removeEventListener('pointerup', release)
    window.removeEventListener('pointercancel', release)
    if (pressed?.start) session.commit()
    pressed = null
    dragging.value = false
  }

  const clear = () => { selected.value = null }

  return { selected, lifted, dragging, press, select, drag, release, clear }
}
