/**
 * One diagram being arranged: its picture as PlantUML drew it, where everything is now, the routes the
 * router answered, and undo and redo. The diagram canvas arranges through it.
 *
 * Lines are PlantUML's own while the picture is arranged automatically. Arranged by hand, a line stays
 * PlantUML's until something that moved touches it, and only those lines are the router's (`fullPass`,
 * the rule the composer draws a stored layout by): taking a picture over routes nothing. From then on
 * a line keeps the course it was shown with until something moves it: each drag frame, and each
 * change, runs the quick pass over the lines touching what moved and the lines whose stated route
 * changed, keeping the rest as they were shown (`routing/kept`). A drop keeps the picture the drag
 * showed — the last frame, routed at once if it was still pending — and undo and redo return to the
 * picture each state was shown with. A resized shape is drawn again by the composer (`drawShapes`),
 * one request at a time.
 */
import { computed, ref, shallowRef, watch } from 'vue'
import { Effect } from 'effect'
import type { Point } from '../../domain/layout/geometry'
import type { Arrangement } from '../../domain/layout/canvasArrangement'
import { drawnArrangement } from '../../domain/layout/canvasArrangement'
import { breachesOf } from '../../domain/layout/canvasBreaches'
import { changedShapes, followPass, fullPass, placementOf, quickPass, textRegions } from '../../domain/layout/canvasRouting'
import type { Placement } from '../../domain/layout/canvasRouting'
import type { Reshaped } from '../../domain/layout/canvasShapeDrawing'
import { stillToReshape } from '../../domain/layout/canvasShapeDrawing'
import type { RoutingResult } from '../../domain/layout/routing/scene'
import type { DrawingNode, LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import { pointsOf } from '../../domain/schemas/diagramLayoutGeometry'
import { shapedLines, withoutElements } from '../../domain/layout/arrangementLayout'
import type { CanvasCommand, GroupingIntent } from '../../ports/diagramWriteBodies'
import type { DiagramOccurrence } from '../../domain/diagramOccurrences'
import type { AuthoredGrouping } from '../../domain/authoredGrouping'
import type { ShapeToDraw } from '../../ports/DiagramLayoutRepository'

/** What a session holds at one moment, and what undo returns to: where shapes are, and whether by hand. */
export interface ArrangementState {
  readonly commands?: readonly CanvasCommand[]
  /** Elements moved into and out of the diagram's own boxes, in order, compiled by the server. */
  readonly regroupings?: readonly GroupingIntent[]
  /** The diagram's boxes as the session states them, once one was renamed, deleted or added (D9). */
  readonly groupings?: readonly AuthoredGrouping[]
  /** Further drawings of elements the diagram already draws, added in this session. */
  readonly occurrences?: readonly DiagramOccurrence[]
  readonly overlays?: readonly Record<string, unknown>[]
  readonly picture?: LayoutGeometry
  readonly addedTypes?: ReadonlyMap<string, string>
  readonly additions?: ReadonlyMap<string, string>
  /** Relations the model holds, drawn on the diagram in this session. */
  readonly drawnRelations?: readonly string[]
  readonly arrangement: Arrangement
  /** Arranged by hand: every line routed. Otherwise the picture is PlantUML's, lines and all. */
  readonly byHand: boolean
  /** Elements removed from the diagram in this session, by alias: drawn no more, with their lines. */
  readonly removed?: ReadonlySet<string>
  /** Where arranging by hand began, the picture taken over: what an edit is counted against. */
  readonly takenOver?: Arrangement
  /** The lines as they were shown in this state, by hand: what undo and redo show again. */
  readonly routed?: RoutingResult
}

/** How long the last pass took: the budget is a drag frame. */
export interface PassTiming {
  readonly kind: 'quick' | 'full' | 'follow'
  readonly ms: number
}

/** Draws shapes again at a new size, in the order asked. */
export type DrawShapes = (shapes: readonly ShapeToDraw[]) => Effect.Effect<readonly DrawingNode[], unknown>

export function useArrangementSession(drawShapes: DrawShapes) {
  /** The picture as PlantUML drew it; what is shown is that, less what the session removed. */
  const drawnPicture = shallowRef<LayoutGeometry | null>(null)
  const state = shallowRef<ArrangementState | null>(null)
  const geometry = computed(() =>
    drawnPicture.value && withoutElements(drawnPicture.value, state.value?.removed ?? new Set()))
  const history = shallowRef<readonly ArrangementState[]>([])
  const future = shallowRef<readonly ArrangementState[]>([])
  const routes = shallowRef<RoutingResult | null>(null)
  const timing = ref<PassTiming | null>(null)
  const reshaped = shallowRef<ReadonlyMap<string, Reshaped>>(new Map())
  const reshapeError = ref<string | null>(null)
  let frame: number | null = null
  let reshaping = false

  const arrangement = computed(() => state.value?.arrangement ?? null)
  /** Where every shape *one* draws is: a removed element is no obstacle and holds no box open. */
  const placementIn = (one: ArrangementState | null): Placement | null => {
    const drawn = geometry.value
    const now = one?.arrangement
    if (!drawn || !now) return null
    const removed = one.removed ?? new Set<string>()
    const kept = removed.size === 0 ? now
      : { ...now, elements: new Map([...now.elements].filter(([alias]) => !removed.has(alias))) }
    return placementOf(drawn, kept)
  }
  const placement = computed(() => placementIn(state.value))

  const reshape = async (): Promise<void> => {
    const drawn = geometry.value
    const where = placement.value
    if (reshaping || !drawn || !where) return
    const shapes = new Map<string, Omit<ShapeToDraw, 'to'>>([
      ...drawn.elements.map((one) => [one.alias, { drawing: one.drawing, box: false, drawn: one.extent }] as const),
      ...drawn.boxes.map((one) => [one.alias, { drawing: one.drawing, box: true, drawn: one.extent }] as const),
    ])
    const now = new Map([...where.elements, ...where.boxes])
    const drawnAt = new Map([...shapes].map(([alias, shape]) => [alias, shape.drawn]))
    const wanted = stillToReshape(drawnAt, now, reshaped.value).flatMap((alias) => {
      const shape = shapes.get(alias)
      const to = now.get(alias)
      return shape && to ? [{ alias, shape: { ...shape, to } }] : []
    })
    if (wanted.length === 0) return
    reshaping = true
    try {
      const drawings = await Effect.runPromise(drawShapes(wanted.map(({ shape }) => shape)))
      if (geometry.value !== drawn) return
      const next = new Map(reshaped.value)
      wanted.forEach(({ alias, shape }, index) => next.set(alias, { at: shape.to, drawing: drawings[index] }))
      reshaped.value = next
      reshapeError.value = null
    } catch (failure) {
      reshapeError.value = failure instanceof Error ? failure.message : String(failure)
      return
    } finally {
      reshaping = false
    }
    await reshape()
  }

  watch(placement, () => { void reshape() })

  /** Each relation's course now, by its place on the picture: routed, else as PlantUML drew it. */
  const courses = computed((): ReadonlyMap<number, readonly Point[]> => {
    const drawn = geometry.value
    if (!drawn) return new Map()
    const routed = routes.value
    if (!routed) return new Map(drawn.relations.map((relation) => [relation.index, pointsOf(relation.course)]))
    return new Map([...routed.routes].map(([key, connector]) => [Number(key), connector.course] as const))
  })

  /** Each rule a line breaks, read only by whoever shows them. */
  const breaches = computed(() => {
    const drawn = geometry.value
    const where = placement.value
    if (!drawn || !where || !routes.value) return []
    const unroutable = new Set(routes.value.unroutable.map(Number))
    return breachesOf(drawn, where, courses.value, textRegions(drawn, where), unroutable)
  })

  const timed = (kind: PassTiming['kind'], pass: () => RoutingResult): RoutingResult => {
    const started = performance.now()
    const result = pass()
    timing.value = { kind, ms: performance.now() - started }
    return result
  }

  const routeEverything = () => {
    const drawn = geometry.value
    const where = placement.value
    const now = arrangement.value
    if (drawn && where && now) routes.value = timed('full', () => fullPass(drawn, where, now.routes))
  }

  /**
   * The lines whose stated ports or bends differ between *before* and *after*, keyed as the router keys
   * them: a label moved along its line leaves the line's course alone.
   */
  const restated = (before: Arrangement, after: Arrangement): ReadonlySet<string> => {
    const drawn = geometry.value
    const course = (one: Arrangement, key: string | undefined) => {
      const route = key === undefined ? undefined : one.routes.get(key)
      return JSON.stringify([route?.from, route?.to, route?.via])
    }
    return new Set(drawn ? shapedLines(drawn, before, after).filter((index) => {
      const key = drawn.relations.find((one) => one.index === index)?.key
      return course(before, key) !== course(after, key)
    }).map(String) : [])
  }

  /**
   * The lines of the state now, routed from those shown in *before*: only what the change moved or
   * reshaped is routed again (`quickPass`).
   */
  const routedFrom = (before: ArrangementState, shown: RoutingResult, changed?: ReadonlySet<string>) => {
    const drawn = geometry.value
    const where = placement.value
    const now = arrangement.value
    const was = placementIn(before)
    if (!drawn || !where || !now || !was) return
    const moved = changed ?? changedShapes(was, where)
    const rerouted = restated(before.arrangement, now)
    routes.value = timed('quick', () => quickPass(drawn, was, where, now.routes, shown.routes, moved, rerouted))
  }

  /**
   * Show *next* at once. By hand: *again*, as undo and redo show a state, with the lines it was shown
   * with; else routed on from the lines shown now where it is the same picture; else routed afresh.
   * PlantUML's lines when not by hand.
   */
  const show = (next: ArrangementState, again = false) => {
    const before = state.value
    const shown = routes.value
    const samePicture = !next.picture || next.picture === drawnPicture.value
    if (!samePicture) {
      drawnPicture.value = next.picture
      reshaped.value = new Map()
    }
    state.value = next
    if (!next.byHand) routes.value = null
    else if (again && next.routed) routes.value = next.routed
    else if (samePicture && before?.byHand && shown) routedFrom(before, shown)
    else routeEverything()
    if (next.byHand && routes.value) state.value = { ...next, routed: routes.value }
  }

  /** Start on *drawn*'s picture, arranged as *start* says. Nothing to undo. */
  const open = (drawn: LayoutGeometry, start: ArrangementState | null = null) => {
    reshaped.value = new Map()
    reshapeError.value = null
    drawnPicture.value = drawn
    history.value = []
    future.value = []
    show({ ...(start ?? { arrangement: drawnArrangement(drawn), byHand: false }), picture: drawn })
  }

  /**
   * A step is about to change the arrangement: the state before it is what undo returns to. On a
   * picture still arranged automatically, the step takes it over first, in the same step, so one undo
   * returns to the automatic picture. Taking over moves nothing and keeps every line PlantUML drew.
   */
  const begin = () => {
    const now = state.value
    if (!geometry.value || !now) return
    history.value = [...history.value, now]
    future.value = []
    if (now.byHand) return
    show({ ...now, byHand: true, takenOver: now.arrangement })
  }

  /** Make *next* the state, as one undoable step. */
  const step = (next: ArrangementState) => {
    begin()
    show(next)
  }

  /**
   * Change the arrangement as one undoable step: *next* is asked after the step has begun, so on a
   * picture still arranged automatically it reads where the takeover put things.
   */
  const change = (next: (drawn: LayoutGeometry, now: Arrangement, where: Placement) => Arrangement) => {
    begin()
    const drawn = geometry.value
    const now = state.value
    const where = placement.value
    if (drawn && now && where) show({ ...now, arrangement: next(drawn, now.arrangement, where), byHand: true })
  }

  /** The frame waiting to be drawn: the state its lines are routed from, and the shapes the drag moved. */
  let pending: { readonly from: ArrangementState; changed: ReadonlySet<string> } | null = null
  /**
   * Where a drag of shapes began: the state and the lines shown then. Its frames only follow (`followPass`)
   * from those lines, so a frame costs what following costs on any picture; the drop routes from them.
   */
  let dragged: { readonly from: ArrangementState; readonly shown: RoutingResult } | null = null

  const drawFrame = () => {
    frame = null
    const shown = routes.value
    if (pending && shown && pending.changed.size > 0) {
      dragged ??= { from: pending.from, shown }
      const [drawn, where, now, changed] = [geometry.value, placement.value, state.value, pending.changed]
      const start = dragged.shown
      if (drawn && where && now) routes.value = timed('follow', () => followPass(drawn, where, now.arrangement.routes, start, changed))
    } else if (pending && shown) {
      routedFrom(pending.from, shown, pending.changed)
    }
    pending = null
  }

  /** One frame of a change: the arrangement reached, and the shapes whose lines it moved. */
  const preview = (next: Arrangement, changed: ReadonlySet<string>) => {
    const from = state.value
    if (!from) return
    if (!routes.value) routeEverything()
    state.value = { ...from, arrangement: next, byHand: true }
    pending = { from: pending?.from ?? dragged?.from ?? from, changed }
    if (frame === null) frame = requestAnimationFrame(drawFrame)
  }

  /**
   * The change is dropped. A drag of shapes is routed now, once, from the lines shown before it: only the
   * lines touching what it moved (`quickPass`). Any other change keeps the lines its last frame showed,
   * routed now if still pending.
   */
  const commit = () => {
    if (frame !== null) cancelAnimationFrame(frame)
    frame = null
    if (pending && pending.changed.size > 0) dragged ??= routes.value ? { from: pending.from, shown: routes.value } : null
    else if (pending) drawFrame()
    pending = null
    if (dragged) routedFrom(dragged.from, dragged.shown)
    dragged = null
    const now = state.value
    if (now?.byHand && routes.value) state.value = { ...now, routed: routes.value }
  }

  const undo = () => {
    const earlier = history.value.at(-1)
    if (!earlier || !state.value) return
    future.value = [state.value, ...future.value]
    history.value = history.value.slice(0, -1)
    show(earlier, true)
  }

  const redo = () => {
    const later = future.value[0]
    if (!later || !state.value) return
    history.value = [...history.value, state.value]
    future.value = future.value.slice(1)
    show(later, true)
  }

  /** Nothing open: what a failed read leaves. */
  const close = () => {
    drawnPicture.value = null
    state.value = null
  }

  return {
    drawnPicture, geometry, state, close, arrangement, history, future, routes, timing, placement, courses, breaches,
    reshaped, reshapeError, open, begin, step, change, preview, commit, undo, redo, routeEverything,
  }
}

export type ArrangementSession = ReturnType<typeof useArrangementSession>
