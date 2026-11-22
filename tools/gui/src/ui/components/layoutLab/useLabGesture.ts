/**
 * The lab's one pointer gesture: press a shape and drag it to move it, or press one of its handles and
 * drag to resize it. Each frame states the arrangement the drag has reached and which shapes it moved;
 * the release commits it. A press without travel only selects.
 *
 * The lab's own gesture, deliberately small: the canvas edit mode's gestures (selection rectangles,
 * modes, takeover) are not decided yet, and nothing here stands in for them.
 */
import { ref } from 'vue'
import type { Ref } from 'vue'
import type { Extent, Point } from '../../../domain/layout/geometry'
import type { Arrangement, Handle } from '../../../domain/layout/lab/labArrangement'
import { SMALLEST_ELEMENT, moved, resized, resizedExtent } from '../../../domain/layout/lab/labArrangement'
import { changedShapes, placementOf } from '../../../domain/layout/lab/labRouting'
import type { Placement } from '../../../domain/layout/lab/labRouting'
import type { LayoutLab } from '../../composables/useLayoutLab'
import type { Lift } from './labPaintOrder'

/** How far a press travels before it is a drag rather than a click. */
const TRAVEL = 4

interface Pressed {
  readonly alias: string
  readonly handle: Handle | null
  readonly from: Point
  readonly arrangement: Arrangement
  readonly placement: Placement
  readonly extent: Extent
  dragging: boolean
}

export function useLabGesture(lab: LayoutLab, svg: Ref<SVGSVGElement | null>) {
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

  const press = (event: PointerEvent, alias: string, handle: Handle | null = null) => {
    const arrangement = lab.arrangement.value
    const placement = lab.placement.value
    const extent = placement?.elements.get(alias) ?? placement?.boxes.get(alias)
    if (!arrangement || !placement || !extent || event.button !== 0) return
    event.stopPropagation()
    // Followed on the window, not by pointer capture: pressing a shape paints it in front, which moves
    // its node, and a moved node loses its capture — the release then landed nowhere.
    window.addEventListener('pointermove', drag)
    window.addEventListener('pointerup', release)
    window.addEventListener('pointercancel', release)
    selected.value = alias
    lifted.value = { alias, how: handle === null ? 'moved' : 'resized' }
    pressed = { alias, handle, from: pointIn(event), arrangement, placement, extent, dragging: false }
  }

  const reached = (state: Pressed, dx: number, dy: number): Arrangement | null => {
    const geometry = lab.geometry.value
    if (!geometry) return null
    if (state.handle === null) return moved(geometry, state.arrangement, state.alias, dx, dy)
    const least = geometry.boxes.some((box) => box.alias === state.alias) ? 1 : SMALLEST_ELEMENT
    return resized(geometry, state.arrangement, state.alias, resizedExtent(state.extent, state.handle, dx, dy, least))
  }

  const drag = (event: PointerEvent) => {
    const state = pressed
    const geometry = lab.geometry.value
    if (!state || !geometry) return
    const at = pointIn(event)
    const dx = Math.round(at.x - state.from.x)
    const dy = Math.round(at.y - state.from.y)
    if (!state.dragging) {
      if (Math.hypot(dx, dy) < TRAVEL) return
      state.dragging = true
      dragging.value = true
      lab.begin()
    }
    const next = reached(state, dx, dy)
    if (next) lab.preview(next, changedShapes(state.placement, placementOf(geometry, next)))
  }

  const release = () => {
    window.removeEventListener('pointermove', drag)
    window.removeEventListener('pointerup', release)
    window.removeEventListener('pointercancel', release)
    if (pressed?.dragging) lab.commit()
    pressed = null
    dragging.value = false
  }

  const clear = () => { selected.value = null }

  return { selected, lifted, dragging, press, drag, release, clear }
}
