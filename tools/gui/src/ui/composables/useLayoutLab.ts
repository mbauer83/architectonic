/**
 * The layout lab's session: one diagram's picture, what has been moved since PlantUML drew it, the
 * routes the router answered, and an undo stack. Nothing here is ever written anywhere.
 *
 * Lines are PlantUML's own until the first change; from then on every line is the router's. While
 * something is dragged, each frame runs the router's quick pass over the lines of what moved; a drop
 * runs the full pass over every line.
 */
import { computed, ref, shallowRef } from 'vue'
import { Effect } from 'effect'
import { labGeometry, labPicture } from '../../adapters/http/HttpLayoutLab'
import type { Point } from '../../domain/layout/geometry'
import type { Arrangement } from '../../domain/layout/lab/labArrangement'
import { drawnArrangement, layoutBlock } from '../../domain/layout/lab/labArrangement'
import { breachesOf, countByTier } from '../../domain/layout/lab/labBreaches'
import type { LabGeometry } from '../../domain/layout/lab/labGeometry'
import { pointsOf } from '../../domain/layout/lab/labGeometry'
import { fullPass, placementOf, quickPass, textRegions } from '../../domain/layout/lab/labRouting'
import type { RoutingResult } from '../../domain/layout/routing/scene'

/** How long the last pass took, to show beside the picture: the budget is a drag frame. */
export interface PassTiming {
  readonly kind: 'quick' | 'full'
  readonly ms: number
}

export function useLayoutLab() {
  const geometry = shallowRef<LabGeometry | null>(null)
  const arrangement = shallowRef<Arrangement | null>(null)
  const history = shallowRef<readonly Arrangement[]>([])
  const routes = shallowRef<RoutingResult | null>(null)
  const timing = ref<PassTiming | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const serverPicture = ref<string | null>(null)
  const serverError = ref<string | null>(null)
  const serverLoading = ref(false)
  let frame: number | null = null

  const placement = computed(() =>
    geometry.value && arrangement.value ? placementOf(geometry.value, arrangement.value) : null)

  /** Each relation's course now, by its place on the picture: routed, else as PlantUML drew it. */
  const courses = computed((): ReadonlyMap<number, readonly Point[]> => {
    const drawn = geometry.value
    if (!drawn) return new Map()
    const routed = routes.value
    if (!routed) return new Map(drawn.relations.map((relation) => [relation.index, pointsOf(relation.course)]))
    return new Map(
      [...routed.routes].map(([key, connector]) => [Number(key), connector.course] as const),
    )
  })

  const breaches = computed(() => {
    const drawn = geometry.value
    const where = placement.value
    if (!drawn || !where || !routes.value) return []
    const unroutable = new Set(routes.value.unroutable.map(Number))
    return breachesOf(drawn, where, courses.value, textRegions(drawn, where), unroutable)
  })

  const counts = computed(() => countByTier(breaches.value))

  const layout = computed(() =>
    geometry.value && arrangement.value ? layoutBlock(geometry.value, arrangement.value) : {})

  const timed = (kind: PassTiming['kind'], pass: () => RoutingResult): RoutingResult => {
    const started = performance.now()
    const result = pass()
    timing.value = { kind, ms: performance.now() - started }
    return result
  }

  const routeEverything = () => {
    const drawn = geometry.value
    const where = placement.value
    if (!drawn || !where) return
    routes.value = timed('full', () => fullPass(drawn, where))
  }

  const load = async (artifactId: string) => {
    loading.value = true
    error.value = null
    serverPicture.value = null
    serverError.value = null
    try {
      const drawn = await Effect.runPromise(labGeometry(artifactId))
      geometry.value = drawn
      arrangement.value = drawnArrangement(drawn)
      history.value = []
      routes.value = null
    } catch (failure) {
      geometry.value = null
      arrangement.value = null
      error.value = failure instanceof Error ? failure.message : String(failure)
    } finally {
      loading.value = false
    }
  }

  /** A change is about to begin: the arrangement before it is what undo returns to. */
  const begin = () => {
    if (!arrangement.value) return
    history.value = [...history.value, arrangement.value]
    if (!routes.value) routeEverything()
  }

  /** One frame of a change: the arrangement it has reached, and the shapes whose lines it moved. */
  const preview = (next: Arrangement, changed: ReadonlySet<string>) => {
    arrangement.value = next
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
    if (!earlier) return
    history.value = history.value.slice(0, -1)
    arrangement.value = earlier
    if (history.value.length === 0) routes.value = null
    else routeEverything()
  }

  const reset = () => {
    if (!geometry.value) return
    arrangement.value = drawnArrangement(geometry.value)
    history.value = []
    routes.value = null
    serverPicture.value = null
  }

  const askServer = async () => {
    const drawn = geometry.value
    if (!drawn) return
    serverLoading.value = true
    serverError.value = null
    try {
      serverPicture.value = await Effect.runPromise(labPicture(drawn.artifact_id, layout.value))
    } catch (failure) {
      serverPicture.value = null
      serverError.value = failure instanceof Error ? failure.message : String(failure)
    } finally {
      serverLoading.value = false
    }
  }

  return {
    geometry, arrangement, history, routes, timing, loading, error,
    placement, courses, breaches, counts, layout,
    serverPicture, serverError, serverLoading,
    load, begin, preview, commit, undo, reset, routeEverything, askServer,
  }
}

export type LayoutLab = ReturnType<typeof useLayoutLab>
