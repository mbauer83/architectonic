/**
 * The canvas's gestures on a line (sketch 02·3–02·5): press a line to select it — or press where it ends
 * on an element's edge (Q33) — then drag an end along its element's outline or round onto another side,
 * drag a segment sideways, drag a bend, double-press the line to add a bend and a bend to remove it, and
 * drag the line's label. Bend placement is the pointer's alone (Q35). An end dragged in line with the
 * line's other end snaps there and shows a guide (02·3); a label picked is nudged by the arrows (02·5).
 *
 * Each drag is one undoable step, begun on the first travel: every frame states the route it reached
 * (`canvasRouteEdits`) and the session routes the line between what is stated; the release tidies a
 * reshaped route (a jog of a few pixels straightened, a bend in line with both neighbours gone) and
 * commits. A line whose relation the diagram does not name by key cannot be stated, so it is only
 * selected.
 */
import { computed, ref } from 'vue'
import type { Ref } from 'vue'
import type { Point } from '../../domain/layout/geometry'
import { distanceBetween } from '../../domain/layout/geometry'
import type { Route } from '../../domain/layout/orthogonal'
import { courseOf } from '../../domain/layout/orthogonal'
import type { End } from '../../domain/layout/canvasRouteEdits'
import {
  bendsShown, labelAnchoredAt, labelCentre, lineAt, lineEndNear, portNear, segmentMoved, tidiedRoute,
  wholeRoute, withBendAdded, withBendAt, withBendRemoved, withEndAt, withRouteStated,
} from '../../domain/layout/canvasRouteEdits'
import { MIDDLE } from '../../domain/layout/canvasLineDrawing'
import { type Guide, inLineGuide } from '../../domain/layout/canvasSnapping'
import type { RoutedConnector } from '../../domain/layout/routing/scene'
import type { ArrangementSession } from './useArrangementSession'
import { followingPointer, pointOnPicture } from '../components/canvas/pointerOnPicture'

/** How far, on screen, a press travels before it is a drag; how near a line's end it picks the line. */
const TRAVEL = 4
const NEAR_AN_END = 6
/** A jog shorter than this, on screen, is straightened when a drag ends; an end snaps in line within it. */
const JOG = 4
const IN_LINE_SNAP = 6
/** How long the in-line guide stays after the drop, as the alignment guides do. */
const GUIDE_LINGERS_MS = 700

type Drag =
  | { readonly kind: 'end'; readonly end: End }
  | { readonly kind: 'segment'; readonly index: number }
  | { readonly kind: 'bend'; readonly index: number }
  | { readonly kind: 'label'; readonly grab: Point }

interface Pressed {
  readonly drag: Drag
  readonly from: Point
  /** What the drag starts from, read once the step has begun. */
  start: { readonly routed: RoutedConnector; readonly stated: Route } | null
  /** The course the drag last reached, which the release tidies. */
  course: readonly Point[] | null
}

export function useLineGesture(
  session: ArrangementSession, svg: Ref<SVGSVGElement | null>, pixel: Ref<number>, onPick: () => void,
) {
  /** The line selected, by its place on the picture; null when none is. */
  const line = ref<number | null>(null)
  /** The bend picked on it, which Delete removes. */
  const bend = ref<number | null>(null)
  /** Whether the selected line's label is being moved: its leader is drawn while it is. */
  const movingLabel = ref(false)
  /** Whether the selected line's label was the last thing pressed: the arrows then nudge it (02·5). */
  const labelPicked = ref(false)
  /** The guide of an end dragged in line with the other end, until a moment after the drop. */
  const guides = ref<readonly Guide[]>([])
  let lingering: ReturnType<typeof setTimeout> | undefined
  let pressed: Pressed | null = null

  const selected = computed(() => lineAt(session.geometry.value, session.arrangement.value, line.value))
  const relation = computed(() => selected.value.relation)
  const routed = computed(() =>
    (line.value === null ? null : session.routes.value?.routes.get(String(line.value)) ?? null))
  const stated = computed((): Route => selected.value.stated)
  /** The bends the selected line shows as handles. */
  const bends = computed((): Point[] => (routed.value ? bendsShown(routed.value.course, stated.value) : []))

  const select = (index: number | null) => {
    if (index !== line.value) bend.value = null
    labelPicked.value = false
    line.value = index
    if (index !== null) onPick()
  }
  const clear = () => select(null)

  const begin = (event: PointerEvent, index: number, drag: Drag) => {
    if (event.button !== 0) return
    event.stopPropagation()
    select(index)
    if (drag.kind === 'bend') bend.value = drag.index
    pressed = { drag, from: pointOnPicture(svg.value, event), start: null, course: null }
    follow(true)
  }

  /** A press on a line selects it. */
  const pressLine = (event: PointerEvent, index: number) => {
    if (event.button !== 0) return
    event.stopPropagation()
    select(index)
  }
  const pressEnd = (event: PointerEvent, end: End) => {
    if (line.value !== null) begin(event, line.value, { kind: 'end', end })
  }
  const pressSegment = (event: PointerEvent, index: number) => {
    if (line.value !== null) begin(event, line.value, { kind: 'segment', index })
  }
  const pressBend = (event: PointerEvent, index: number) => {
    if (line.value !== null) begin(event, line.value, { kind: 'bend', index })
  }
  const pressLabel = (event: PointerEvent, index: number) => {
    const course = session.courses.value.get(index)
    if (!course) return
    const { stated: route } = lineAt(session.geometry.value, session.arrangement.value, index)
    const centre = labelCentre(course, route.label ?? MIDDLE)
    const at = pointOnPicture(svg.value, event)
    begin(event, index, { kind: 'label', grab: { x: at.x - centre.x, y: at.y - centre.y } })
    labelPicked.value = event.button === 0
  }

  /**
   * A press on an element where a line ends on its edge picks that line and drags its end (Q33);
   * answers whether the press was taken.
   */
  const pressNearAnEnd = (event: PointerEvent): boolean => {
    if (event.button !== 0 || session.routes.value === null) return false
    const near = lineEndNear(session.courses.value, pointOnPicture(svg.value, event), NEAR_AN_END * pixel.value)
    if (!near) return false
    begin(event, near.line, { kind: 'end', end: near.end })
    return true
  }

  const endExtent = (end: End) => {
    const alias = end === 'from' ? relation.value?.source : relation.value?.target
    const where = session.placement.value
    return alias === undefined || !where ? undefined : where.elements.get(alias) ?? where.boxes.get(alias)
  }

  /** The route the drag has reached at *at*, and the course it is drawn along where the drag decides it. */
  const reached = (state: Pressed, at: Point): { route: Route; course: readonly Point[] | null } | null => {
    const start = state.start
    const now = relation.value
    if (!start || !now) return null
    const drag = state.drag
    if (drag.kind === 'end') {
      const extent = endExtent(drag.end)
      if (!extent) return null
      const other = drag.end === 'from' ? start.routed.course.at(-1) : start.routed.course[0]
      const port = portNear(extent, at, other ?? null, IN_LINE_SNAP * pixel.value)
      const guide = inLineGuide(extent, port, other ?? null)
      guides.value = guide ? [guide] : []
      return { route: withEndAt(start.stated, drag.end, port, extent), course: null }
    }
    if (drag.kind === 'segment') {
      const [a, b] = [start.routed.course[drag.index], start.routed.course[drag.index + 1]]
      const level = Math.abs(a.y - b.y) < 0.5
      const course = segmentMoved(start.routed, now.decorated, drag.index, level ? at.y : at.x)
      return { route: tidiedRoute(course, start.routed, 0, start.stated), course }
    }
    if (drag.kind === 'bend') {
      return { route: withBendAt(wholeRoute(start.stated, start.routed), drag.index, at), course: null }
    }
    const centre = { x: at.x - drag.grab.x, y: at.y - drag.grab.y }
    return { route: { ...start.stated, label: labelAnchoredAt(start.routed.course, centre) }, course: null }
  }

  const stateAs = (route: Route) => {
    const key = relation.value?.key
    const now = session.arrangement.value
    if (key !== undefined && now) session.preview(withRouteStated(now, key, route), new Set())
  }

  const moved = (event: PointerEvent) => {
    const state = pressed
    if (!state || line.value === null) return
    const at = pointOnPicture(svg.value, event)
    if (!state.start) {
      if (distanceBetween(at, state.from) < TRAVEL * pixel.value || relation.value?.key === undefined) return
      session.begin()
      const routedNow = routed.value
      if (!routedNow) return
      state.start = { routed: routedNow, stated: stated.value }
      movingLabel.value = state.drag.kind === 'label'
    }
    const next = reached(state, at)
    if (!next) return
    state.course = next.course
    stateAs(next.route)
  }

  /** The route a reshaping drag ends on, tidied; the stated route as it is for any other drag. */
  const tidied = (state: Pressed): Route | null => {
    const start = state.start
    const now = relation.value
    if (!start || !now || (state.drag.kind !== 'segment' && state.drag.kind !== 'bend')) return null
    const [source, target] = [endExtent('from'), endExtent('to')]
    const route = stated.value
    const course = state.course ?? (source && target ? courseOf(route, source, target) : null)
    if (!course || !route.from || !route.to) return null
    return tidiedRoute(course, { ...start.routed, sourcePort: route.from, targetPort: route.to, course },
      JOG * pixel.value, route)
  }

  const released = () => {
    follow(false)
    const state = pressed
    pressed = null
    movingLabel.value = false
    clearTimeout(lingering)
    lingering = setTimeout(() => { guides.value = [] }, GUIDE_LINGERS_MS)
    if (!state?.start) return
    const tidy = tidied(state)
    if (tidy) {
      stateAs(tidy)
      bend.value = null
    }
    session.commit()
  }

  const follow = followingPointer(moved, released)

  /** Change the selected line's stated route as one undoable step. */
  const restate = (next: (route: Route, routedNow: RoutedConnector) => Route) => {
    const key = relation.value?.key
    const routedNow = routed.value
    if (key === undefined || !routedNow) return
    session.change((_drawn, now) => withRouteStated(now, key, next(now.routes.get(key) ?? {}, routedNow)))
  }

  /** A double press on the selected line adds a bend there; on one of its bends, removes it. */
  const doublePress = (event: MouseEvent, bendIndex: number | null = null) => {
    if (line.value === null) return
    event.stopPropagation()
    if (bendIndex !== null) {
      restate((route, routedNow) => withBendRemoved(wholeRoute(route, routedNow), bendIndex))
      bend.value = null
      return
    }
    const at = pointOnPicture(svg.value, event)
    restate((route, routedNow) => withBendAdded(routedNow, at, route))
  }

  /** Delete on a picked bend removes it; answers whether there was one. */
  const removePickedBend = (): boolean => {
    const picked = bend.value
    if (picked === null || line.value === null) return false
    restate((route, routedNow) => withBendRemoved(wholeRoute(route, routedNow), picked))
    bend.value = null
    return true
  }

  /** The arrows on a picked label: moved by (dx, dy) and anchored again, as one step; answers whether one was. */
  const nudgeLabel = (dx: number, dy: number): boolean => {
    const course = line.value === null ? undefined : session.courses.value.get(line.value)
    if (!labelPicked.value || !course) return false
    restate((route) => {
      const centre = labelCentre(course, route.label ?? MIDDLE)
      return { ...route, label: labelAnchoredAt(course, { x: centre.x + dx, y: centre.y + dy }) }
    })
    return true
  }

  return {
    line, bend, bends, routed, stated, movingLabel, guides, labelPicked, select, clear, nudgeLabel,
    pressLine, pressEnd, pressSegment, pressBend, pressLabel, pressNearAnEnd, doublePress, removePickedBend,
  }
}
