/**
 * Where the title and the legend of a diagram being arranged are drawn (owner, 2026-11-25): where the saved
 * picture will draw them.
 *
 * The rule is the composer's and stays there (`surround_placement.py`): the canvas asks the layout surround
 * route with where the diagram is now and draws each part moved by what it answers. It asks once the
 * picture settles — a pause in a drag, a drop, an undo — rather than every frame, and an answer to an older
 * question is not drawn. A picture PlantUML still arranges is drawn as PlantUML drew it, title and legend
 * where they are, so nothing is asked for it.
 */
import { computed, shallowRef, watch } from 'vue'
import { Effect } from 'effect'
import type { Extent, Point } from '../../domain/layout/geometry'
import { labelCentre } from '../../domain/layout/canvasRouteEdits'
import { MIDDLE } from '../../domain/layout/canvasLineDrawing'
import type { SurroundPart } from '../../domain/schemas/diagramLayoutGeometry'
import type { SurroundPlacement } from '../../ports/DiagramLayoutRepository'
import { createDebouncer } from '../lib/debounce'
import type { ArrangementSession } from './useArrangementSession'

/** How long the picture rests before the parts round it are placed again. */
const SETTLED_MS = 120

/** A part drawn round the diagram, how far it is carried from where PlantUML drew it, and where it is now. */
export interface PlacedPart {
  readonly part: SurroundPart
  readonly by: Point
  readonly extent: Extent
}

type Moves = readonly (readonly [number, number])[]
type Place = (placement: SurroundPlacement) => Effect.Effect<Moves, unknown>

/** Where the diagram of *session* is now, as the surround route reads it; null where nothing is open. */
export const placementOf = (session: ArrangementSession): SurroundPlacement | null => {
  const drawn = session.geometry.value
  const where = session.placement.value
  const now = session.arrangement.value
  if (!drawn || !where || !now) return null
  const courses = session.courses.value
  const labels = drawn.relations.flatMap((relation) => {
    const course = courses.get(relation.index)
    if (!relation.label_size || !course?.length) return []
    const anchor = (relation.key === undefined ? undefined : now.routes.get(relation.key)?.label) ?? MIDDLE
    const centre = labelCentre(course, anchor)
    const [width, height] = relation.label_size
    const [x, y] = [width / 2, height / 2]
    return [{ left: centre.x - x, top: centre.y - y, right: centre.x + x, bottom: centre.y + y }]
  })
  return {
    drawn: drawn.surround.drawn,
    parts: drawn.surround.parts.map((part) => part.extent),
    shapes: [...where.elements.values(), ...where.boxes.values()],
    courses: [...courses.values()].map((course) => course.map(({ x, y }) => [x, y] as const)),
    labels,
  }
}

export function useSurroundPlacement(session: ArrangementSession, place: Place) {
  const moves = shallowRef<Moves>([])
  const settled = createDebouncer(SETTLED_MS)
  let asked = 0

  const ask = () => {
    const question = ++asked
    const placement = session.state.value?.byHand ? placementOf(session) : null
    if (!placement || placement.parts.length === 0) {
      moves.value = []
      return
    }
    void Effect.runPromise(place(placement)).then((answer) => {
      if (question === asked) moves.value = answer
    }, () => { /* the parts stay where they were last placed */ })
  }
  watch(() => [session.state.value, session.routes.value], () => settled(ask))
  watch(() => session.geometry.value, () => { moves.value = []; ask() })

  return computed((): PlacedPart[] => (session.geometry.value?.surround.parts ?? []).map((part, index) => {
    const [x, y] = moves.value[index] ?? [0, 0]
    const { left, top, right, bottom } = part.extent
    return { part, by: { x, y }, extent: { left: left + x, top: top + y, right: right + x, bottom: bottom + y } }
  }))
}
