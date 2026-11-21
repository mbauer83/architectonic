/**
 * Routes every connector of a scene: ports and stubs, a search each, then nudging.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/router.py`: sides chosen by a search
 * from every side to every side, ports spread along the sides they share, each connector searched
 * again between its own ports, then nudging. A connector from an element to itself loops round its
 * corner; between a box and an element inside it, one straight run; between elements closer than a
 * stub, the most direct way. One no route reaches is unroutable, never drawn through something.
 * With `previous` and `changed`, only the connectors of what moved are routed and nudged: a drag's
 * quick pass.
 */
import type { Extent, Point } from '../geometry'
import type { Port } from '../orthogonal'
import { STUB } from '../orthogonal'
import { nudged } from './nudging'
import type { Stub } from './ports'
import { OUTWARD_INDEX, inLine, stubOf } from './ports'
import type { Choice, Connector, RoutedConnector, RoutingResult, RoutingScene } from './scene'
import { IDEAL_SEPARATION, SIDES, byText, extentOf, runFor } from './scene'
import type { Found } from './search'
import { DIRECTIONS, REVERSE, search } from './search'
import type { Passage } from './visibility'
import { Lines, Stubs } from './lines'
import { FULL, Visibility } from './visibility'
import { special } from './special'
import { portsSpread } from './spreading'

/** Far enough to stand for everywhere outside a box. */
const FAR_OUT = 1.0e7

/** Everything outside *box*, as four rectangles: what nudging keeps a route inside its box by. */
const outside = (box: Extent | null): Extent[] =>
  box
    ? [
        { left: -FAR_OUT, top: -FAR_OUT, right: box.left, bottom: FAR_OUT },
        { left: box.right, top: -FAR_OUT, right: FAR_OUT, bottom: FAR_OUT },
        { left: -FAR_OUT, top: -FAR_OUT, right: FAR_OUT, bottom: box.top },
        { left: -FAR_OUT, top: box.bottom, right: FAR_OUT, bottom: FAR_OUT },
      ]
    : []

/**
 * Every stub the routes will leave and arrive by: those of the ports chosen, reaching on by the ideal
 * separation as nudging may lengthen them, and the first and last runs of the routes drawn already.
 */
const stubLines = (
  scene: RoutingScene,
  connectors: readonly Connector[],
  ports: ReadonlyMap<string, readonly [Choice, Choice]>,
  drawn: readonly RoutedConnector[],
): Stubs => {
  const lines = new Stubs()
  for (const connector of connectors) {
    const chosen = ports.get(connector.key)
    if (!chosen) continue
    ;[connector.source, connector.target].forEach((end, which) => {
      const [side, at] = chosen[which]
      const stub = stubOf(extentOf(scene, end), side, at, runFor(connector.decorated[which]) + IDEAL_SEPARATION)
      lines.add(stub.at, stub.end, connector.key)
    })
  }
  for (const routed of drawn) {
    const course = routed.course
    lines.add(course[0], course[1], routed.key)
    lines.add(course[course.length - 2], course[course.length - 1], routed.key)
  }
  return lines
}

const sidesOf = (port: Port | undefined): Choice[] =>
  port ? [[port.side, port.at]] : SIDES.map((side): Choice => [side, 0.5])

const lengthBetween = (a: Point, b: Point): number => Math.abs(b.x - a.x) + Math.abs(b.y - a.y)

const faces = (start: Stub, goal: Stub): boolean => {
  const dx = goal.at.x - start.at.x
  const dy = goal.at.y - start.at.y
  const [outX, outY] = DIRECTIONS[OUTWARD_INDEX[start.port.side]]
  return dx * outY === 0 && dy * outX === 0 && dx * outX + dy * outY >= STUB
}

const acrossStub = (stub: Stub): Extent => {
  const a = stub.at
  const b = stub.end
  if (a.x === b.x) {
    const [top, bottom] = b.y > a.y ? [a.y, b.y - 1] : [b.y + 1, a.y]
    return { left: a.x - 1, top, right: a.x + 1, bottom }
  }
  const [left, right] = b.x > a.x ? [a.x, b.x - 1] : [b.x + 1, a.x]
  return { left, top: a.y - 1, right, bottom: a.y + 1 }
}

/** Whether *stub* is clear, walked the way the route walks it: out of a source, into a target. */
const usable = (stub: Stub, passage: Passage, own: readonly Extent[], arriving: boolean): boolean =>
  !passage.pointBlocked(stub.end) &&
  !(arriving ? passage.stepBlocked(stub.end, stub.at, own) : passage.stepBlocked(stub.at, stub.end, own))

const straightened = (points: readonly Point[]): Point[] => {
  const kept = [points[0]]
  for (let index = 1; index < points.length - 1; index += 1) {
    const before = kept[kept.length - 1]
    const here = points[index]
    const after = points[index + 1]
    const repeat = here.x === before.x && here.y === before.y
    const upright = before.x === here.x && here.x === after.x
    const level = before.y === here.y && here.y === after.y
    if (!repeat && !upright && !level) kept.push(here)
  }
  return [...kept, points[points.length - 1]]
}

class Routing {
  readonly visibility: Visibility
  readonly crowd = new Lines()

  constructor(readonly scene: RoutingScene) {
    this.visibility = new Visibility(scene)
    for (const line of scene.fixedLines) line.slice(1).forEach((b, index) => this.crowd.add(line[index], b))
  }

  taken(routed: RoutedConnector): void {
    routed.course.slice(1).forEach((b, index) => this.crowd.add(routed.course[index], b))
  }

  own(connector: Connector): Extent[] {
    return [connector.source, connector.target].flatMap((end) => {
      const grown = this.visibility.grown.get(end)
      return grown ? [grown] : []
    })
  }

  private stubs(connector: Connector, which: number, choices: readonly Choice[], passage: Passage): Stub[] {
    const extent = extentOf(this.scene, which === 0 ? connector.source : connector.target)
    const run = runFor(connector.decorated[which])
    const own = this.own(connector)
    return choices
      .map(([side, at]) => stubOf(extent, side, at, run))
      .filter((stub) => usable(stub, passage, own, which === 1))
  }

  /**
   * The cheapest route between the choices of ports, or null: within the connector's bounds, and
   * without them only where no route keeps them. With *liningUp*, ports on facing sides are also tried
   * lined up for a straight run; without, the ports are as chosen. *stubs* are the other connectors'
   * stubs, which no run goes along.
   */
  searched(
    connector: Connector,
    sources: readonly Choice[],
    targets: readonly Choice[],
    liningUp = true,
    stubs: Stubs | null = null,
  ): RoutedConnector | null {
    const bounded = this.visibility.passage([connector.source, connector.target])
    for (const passage of [bounded, bounded.unbounded()]) {
      const found = this.searchedIn(connector, sources, targets, passage, liningUp, stubs)
      if (found) return found
    }
    return null
  }

  private searchedIn(
    connector: Connector,
    sources: readonly Choice[],
    targets: readonly Choice[],
    bounded: Passage,
    liningUp: boolean,
    stubs: Stubs | null,
  ): RoutedConnector | null {
    let passage = bounded
    const starts = this.stubs(connector, 0, sources, passage)
    const goals = this.stubs(connector, 1, targets, passage)
    const [linedStarts, linedGoals] = liningUp ? this.linedUp(connector, sources, targets) : [[], []]
    const crowded = passage.adding([], this.crowd)
    const straight = this.straight(connector, [...linedStarts, ...starts], [...linedGoals, ...goals], crowded)
    if (straight) return straight
    if (starts.length === 0 || goals.length === 0) return null
    passage = passage.adding([...starts, ...goals].map(acrossStub), this.crowd, stubs ? [stubs, connector.key] : null)
    const found = search(
      starts.map((stub, tag) => ({ point: stub.end, direction: OUTWARD_INDEX[stub.port.side], tag })),
      goals.map((stub, tag) => ({ point: stub.end, direction: REVERSE[OUTWARD_INDEX[stub.port.side]], tag })),
      passage,
      this.visibility.graph,
    )
    return found ? asRouted(connector, found, starts, goals) : null
  }

  private linedUp(connector: Connector, sources: readonly Choice[], targets: readonly Choice[]): [Stub[], Stub[]] {
    const source = extentOf(this.scene, connector.source)
    const target = extentOf(this.scene, connector.target)
    const starts: Stub[] = []
    const goals: Stub[] = []
    if (connector.sourcePort || connector.targetPort) return [starts, goals]
    for (const [side] of sources) {
      for (const [other] of targets) {
        const lined = inLine(source, target, [side, other])
        if (lined) {
          starts.push(stubOf(source, side, lined[0], 0))
          goals.push(stubOf(target, other, lined[1], 0))
        }
      }
    }
    return [starts, goals]
  }

  private straight(
    connector: Connector,
    starts: readonly Stub[],
    goals: readonly Stub[],
    passage: Passage,
  ): RoutedConnector | null {
    const own = this.own(connector)
    let best: readonly [Stub, Stub] | null = null
    for (const start of starts) {
      for (const goal of goals) {
        if (
          REVERSE[OUTWARD_INDEX[start.port.side]] === OUTWARD_INDEX[goal.port.side] &&
          faces(start, goal) &&
          !passage.stepBlocked(start.at, goal.at, own) &&
          passage.crowding(start.at, goal.at) < FULL &&
          (best === null || lengthBetween(start.at, goal.at) < lengthBetween(best[0].at, best[1].at))
        ) {
          best = [start, goal]
        }
      }
    }
    if (!best) return null
    return { key: connector.key, sourcePort: best[0].port, targetPort: best[1].port, course: [best[0].at, best[1].at] }
  }

}

const asRouted = (
  connector: Connector,
  found: Found,
  starts: readonly Stub[],
  goals: readonly Stub[],
): RoutedConnector => {
  const start = starts[found.start]
  const goal = goals[found.goal]
  return {
    key: connector.key,
    sourcePort: start.port,
    targetPort: goal.port,
    course: straightened([start.at, ...found.points, goal.at]),
  }
}

export interface QuickPass {
  readonly previous: ReadonlyMap<string, RoutedConnector>
  readonly changed: ReadonlySet<string>
}

/** Every connector's route, the unroutable ones, and what nudging could not separate. */
export const routeAll = (
  scene: RoutingScene,
  connectors: readonly Connector[],
  quick: QuickPass | null = null,
): RoutingResult => {
  const routing = new Routing(scene)
  const ordered = [...connectors].sort((one, other) => byText(one.key, other.key))
  const kept = new Map<string, RoutedConnector>()
  let toRoute = ordered
  if (quick) {
    const touched = ordered.filter(
      (one) => quick.changed.has(one.source) || quick.changed.has(one.target) || !quick.previous.has(one.key),
    )
    for (const one of ordered) {
      const before = quick.previous.get(one.key)
      if (!touched.includes(one) && before) kept.set(one.key, before)
    }
    toRoute = touched
  }
  for (const routed of kept.values()) routing.taken(routed)
  const routes = new Map<string, RoutedConnector>()
  const unroutable: string[] = []
  const searched: Connector[] = []
  const first = new Map<string, RoutedConnector>()
  for (const connector of toRoute) {
    const made = special(scene, routing.visibility, connector, routing.own(connector))
    if (made === true) {
      searched.push(connector)
      const again = quick?.previous.get(connector.key)
      const found =
        (again
          ? routing.searched(connector, [[again.sourcePort.side, 0.5]], [[again.targetPort.side, 0.5]])
          : null) ?? routing.searched(connector, sidesOf(connector.sourcePort), sidesOf(connector.targetPort))
      if (found) first.set(connector.key, found)
      else unroutable.push(connector.key)
    } else if (made === null) {
      unroutable.push(connector.key)
    } else {
      routes.set(connector.key, made)
      routing.taken(made)
    }
  }
  const spreadPorts = portsSpread(scene, searched, first)
  const stubs = stubLines(scene, searched, spreadPorts, [...kept.values(), ...routes.values()])
  for (const [key, [source, target]] of spreadPorts) {
    const connector = searched.find((one) => one.key === key)
    const before = first.get(key)
    if (!connector || !before) continue
    const routed = routing.searched(connector, [source], [target], false, stubs) ?? before
    routes.set(key, routed)
    routing.taken(routed)
  }
  const every = new Map([...kept, ...routes])
  const courses = new Map([...every].map(([key, routed]) => [key, [...routed.course]]))
  const obstacles = new Map(
    ordered
      .filter((connector) => courses.has(connector.key))
      .map((connector) => [
        connector.key,
        [
          ...routing.visibility.grown.values(),
          ...scene.text.values(),
          ...routing.visibility.passage([connector.source, connector.target]).walls,
          ...outside(routing.visibility.bounds([connector.source, connector.target]).within),
        ],
      ]),
  )
  const [moved, unseparated] = nudged(
    courses,
    obstacles,
    [...scene.boxes.values()],
    scene.fixedLines,
    quick ? new Set(routes.keys()) : null,
  )
  const keys = [...every.keys()].sort(byText)
  return {
    routes: new Map(
      keys.map((key) => {
        const routed = every.get(key) as RoutedConnector
        return [key, { ...routed, course: moved.get(key) ?? routed.course }]
      }),
    ),
    unroutable,
    unseparated,
  }
}
