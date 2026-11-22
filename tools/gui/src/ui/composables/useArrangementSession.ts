/**
 * One diagram being arranged: its picture as PlantUML drew it, where everything is now, the routes the
 * router answered, and undo and redo. The diagram canvas and the layout lab both arrange through it.
 *
 * Lines are PlantUML's own while the picture is arranged automatically; once it is arranged by hand
 * every line is the router's. While something is dragged, each frame runs the router's quick pass over
 * the lines of what moved; a drop runs the full pass over every line. A resized shape is drawn again by
 * the composer (`drawShapes`), one request at a time.
 */
import { computed, ref, shallowRef, watch } from 'vue'
import { Effect } from 'effect'
import type { Point } from '../../domain/layout/geometry'
import type { Arrangement } from '../../domain/layout/lab/labArrangement'
import { drawnArrangement } from '../../domain/layout/lab/labArrangement'
import { breachesOf } from '../../domain/layout/lab/labBreaches'
import { fullPass, placementOf, quickPass, textRegions } from '../../domain/layout/lab/labRouting'
import type { Reshaped } from '../../domain/layout/lab/labShapeDrawing'
import { stillToReshape } from '../../domain/layout/lab/labShapeDrawing'
import type { RoutingResult } from '../../domain/layout/routing/scene'
import type { DrawingNode, LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import { pointsOf } from '../../domain/schemas/diagramLayoutGeometry'
import { withoutElements } from '../../domain/layout/arrangementLayout'
import type { ShapeToDraw } from '../../ports/DiagramLayoutRepository'

/** What a session holds at one moment, and what undo returns to: where shapes are, and whether by hand. */
export interface ArrangementState {
  readonly arrangement: Arrangement
  /** Arranged by hand: every line routed. Otherwise the picture is PlantUML's, lines and all. */
  readonly byHand: boolean
  /** Elements removed from the diagram in this session, by alias: drawn no more, with their lines. */
  readonly removed?: ReadonlySet<string>
}

/** How long the last pass took: the budget is a drag frame. */
export interface PassTiming {
  readonly kind: 'quick' | 'full'
  readonly ms: number
}

/** Draws shapes again at a new size, in the order asked. */
export type DrawShapes = (shapes: readonly ShapeToDraw[]) => Effect.Effect<readonly DrawingNode[], unknown>

/** What arranging by hand starts from, given PlantUML's arrangement of the picture. */
export type TakeOver = (geometry: LayoutGeometry, automatic: Arrangement) => Arrangement

export function useArrangementSession(drawShapes: DrawShapes, takeOver: TakeOver) {
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
  /** Where every shape now drawn is: a removed element is no obstacle and holds no box open. */
  const placement = computed(() => {
    const drawn = geometry.value
    const now = arrangement.value
    if (!drawn || !now) return null
    const removed = state.value?.removed ?? new Set<string>()
    const kept = removed.size === 0 ? now
      : { ...now, elements: new Map([...now.elements].filter(([alias]) => !removed.has(alias))) }
    return placementOf(drawn, kept)
  })

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
    if (drawn && where) routes.value = timed('full', () => fullPass(drawn, where))
  }

  /** Show *next* at once: lines routed afresh when by hand, PlantUML's when not. */
  const show = (next: ArrangementState) => {
    state.value = next
    if (next.byHand) routeEverything()
    else routes.value = null
  }

  /** Start on *drawn*'s picture, arranged as *start* says. Nothing to undo. */
  const open = (drawn: LayoutGeometry, start: ArrangementState | null = null) => {
    reshaped.value = new Map()
    reshapeError.value = null
    drawnPicture.value = drawn
    history.value = []
    future.value = []
    show(start ?? { arrangement: drawnArrangement(drawn), byHand: false })
  }

  /**
   * A step is about to change the arrangement: the state before it is what undo returns to. On a
   * picture still arranged automatically, the step takes it over first (`takeOver`), in the same step,
   * so one undo returns to the automatic picture.
   */
  const begin = () => {
    const drawn = geometry.value
    const now = state.value
    if (!drawn || !now) return
    history.value = [...history.value, now]
    future.value = []
    if (!now.byHand) show({ ...now, arrangement: takeOver(drawn, now.arrangement), byHand: true })
  }

  /** Make *next* the state, as one undoable step. */
  const step = (next: ArrangementState) => {
    begin()
    show(next)
  }

  /** One frame of a change: the arrangement reached, and the shapes whose lines it moved. */
  const preview = (next: Arrangement, changed: ReadonlySet<string>) => {
    state.value = { ...state.value, arrangement: next, byHand: true }
    if (!routes.value) routeEverything()
    if (frame !== null) return
    frame = requestAnimationFrame(() => {
      frame = null
      const drawn = geometry.value
      const where = placement.value
      const previous = routes.value
      if (!drawn || !where || !previous) return
      routes.value = timed('quick', () => quickPass(drawn, where, previous.routes, changed))
    })
  }

  /** The change is dropped: every line routed afresh. */
  const commit = () => {
    if (frame !== null) cancelAnimationFrame(frame)
    frame = null
    routeEverything()
  }

  const undo = () => {
    const earlier = history.value.at(-1)
    if (!earlier || !state.value) return
    future.value = [state.value, ...future.value]
    history.value = history.value.slice(0, -1)
    show(earlier)
  }

  const redo = () => {
    const later = future.value[0]
    if (!later || !state.value) return
    history.value = [...history.value, state.value]
    future.value = future.value.slice(1)
    show(later)
  }

  /** Nothing open: what a failed read leaves. */
  const close = () => {
    drawnPicture.value = null
    state.value = null
  }

  return {
    drawnPicture, geometry, state, close, arrangement, history, future, routes, timing, placement, courses, breaches,
    reshaped, reshapeError, open, begin, step, preview, commit, undo, redo, routeEverything,
  }
}

export type ArrangementSession = ReturnType<typeof useArrangementSession>
