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
import { endsConflict, formedAfresh, fraction } from '../attachment'
import type { Extent, Point } from '../geometry'
import { centreOf, encloses, heightOf, widthOf } from '../geometry'
import type { Port, Side } from '../orthogonal'
import { STUB, courseOf, leavesLevel } from '../orthogonal'
import { nudged } from './nudging'
import type { EndOnSide, Stub } from './ports'
import { OUTWARD_INDEX, inLine, spread, stubOf } from './ports'
import type { Connector, RoutedConnector, RoutingResult, RoutingScene } from './scene'
import { SIDES, byText, extentOf, runFor } from './scene'
import type { Found } from './search'
import { DIRECTIONS, REVERSE, search } from './search'
import type { Passage } from './visibility'
import { FULL, Lines, Visibility } from './visibility'

type Choice = readonly [Side, number]

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

const usable = (stub: Stub, passage: Passage, own: readonly Extent[]): boolean =>
  !passage.pointBlocked(stub.end) && !passage.stepBlocked(stub.at, stub.end, own)

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

const shareAlong = (extent: Extent, coordinate: number, level: boolean): number => {
  const length = level ? heightOf(extent) : widthOf(extent)
  return length > 0 ? (coordinate - (level ? extent.top : extent.left)) / length : 0.5
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

  private own(connector: Connector): Extent[] {
    return [connector.source, connector.target].flatMap((end) => {
      const grown = this.visibility.grown.get(end)
      return grown ? [grown] : []
    })
  }

  private stubs(connector: Connector, which: number, choices: readonly Choice[], passage: Passage): Stub[] {
    const extent = extentOf(this.scene, which === 0 ? connector.source : connector.target)
    const run = runFor(connector.decorated[which])
    const own = this.own(connector)
    return choices.map(([side, at]) => stubOf(extent, side, at, run)).filter((stub) => usable(stub, passage, own))
  }

  /**
   * The cheapest route between the choices of ports, or null. With *liningUp*, ports on facing sides
   * are also tried lined up for a straight run; without, the ports are as chosen — spread along a side
   * another end shares, which a straight run lined up elsewhere would undo.
   */
  searched(
    connector: Connector,
    sources: readonly Choice[],
    targets: readonly Choice[],
    liningUp = true,
  ): RoutedConnector | null {
    let passage = this.visibility.passage([connector.source, connector.target])
    const starts = this.stubs(connector, 0, sources, passage)
    const goals = this.stubs(connector, 1, targets, passage)
    const [linedStarts, linedGoals] = liningUp ? this.linedUp(connector, sources, targets) : [[], []]
    const crowded = passage.adding([], this.crowd)
    const straight = this.straight(connector, [...linedStarts, ...starts], [...linedGoals, ...goals], crowded)
    if (straight) return straight
    if (starts.length === 0 || goals.length === 0) return null
    passage = passage.adding([...starts, ...goals].map(acrossStub), this.crowd)
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

  special(connector: Connector): RoutedConnector | null | true {
    const source = extentOf(this.scene, connector.source)
    const target = extentOf(this.scene, connector.target)
    if (connector.source === connector.target) return aroundItself(connector, source)
    if (encloses(source, target) || encloses(target, source)) return this.wholeToPart(connector, source, target)
    if (endsConflict(source, target)) {
      const made = formedAfresh({}, source, target)
      const course = courseOf(made, source, target)
      if (made.from && made.to && course) {
        return { key: connector.key, sourcePort: made.from, targetPort: made.to, course }
      }
    }
    return true
  }

  private wholeToPart(connector: Connector, source: Extent, target: Extent): RoutedConnector | null {
    const wholeIsSource = encloses(source, target)
    const whole = wholeIsSource ? source : target
    const part = wholeIsSource ? target : source
    const partKey = wholeIsSource ? connector.target : connector.source
    const passage = this.visibility.passage([partKey, partKey])
    const gaps: Record<Side, number> = {
      top: part.top - whole.top,
      bottom: whole.bottom - part.bottom,
      left: part.left - whole.left,
      right: whole.right - part.right,
    }
    const order = [...SIDES].sort((one, other) => gaps[one] - gaps[other] || SIDES.indexOf(one) - SIDES.indexOf(other))
    for (const side of order) {
      const stub = stubOf(part, side, 0.5, 0)
      const borders: Record<Side, Point> = {
        top: { x: stub.at.x, y: whole.top },
        bottom: { x: stub.at.x, y: whole.bottom },
        left: { x: whole.left, y: stub.at.y },
        right: { x: whole.right, y: stub.at.y },
      }
      const border = borders[side]
      if (passage.stepBlocked(stub.at, border, this.own(connector))) continue
      const level = leavesLevel(side)
      const wholePort: Port = { side, at: fraction(shareAlong(whole, level ? border.y : border.x, level)) }
      return wholeIsSource
        ? { key: connector.key, sourcePort: wholePort, targetPort: stub.port, course: [border, stub.at] }
        : { key: connector.key, sourcePort: stub.port, targetPort: wholePort, course: [stub.at, border] }
    }
    return null
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

const aroundItself = (connector: Connector, extent: Extent): RoutedConnector => {
  const leaving = stubOf(extent, 'right', 0.7, runFor(connector.decorated[0]))
  const arriving = stubOf(extent, 'bottom', 0.7, runFor(connector.decorated[1]))
  const corner = { x: leaving.end.x, y: arriving.end.y }
  return {
    key: connector.key,
    sourcePort: leaving.port,
    targetPort: arriving.port,
    course: [leaving.at, leaving.end, corner, arriving.end, arriving.at],
  }
}

const endsOnSides = (
  routing: Routing,
  connectors: readonly Connector[],
  first: ReadonlyMap<string, RoutedConnector>,
): EndOnSide[] =>
  connectors.flatMap((connector) => {
    const routed = first.get(connector.key)
    if (!routed) return []
    const both = [
      [routed.sourcePort, connector.sourcePort, connector.target, connector.source],
      [routed.targetPort, connector.targetPort, connector.source, connector.target],
    ] as const
    return both.flatMap(([port, stated, other, element], which): EndOnSide[] => {
      if (stated) return []
      const centre = centreOf(extentOf(routing.scene, other))
      const toward = leavesLevel(port.side) ? centre.y : centre.x
      return [{ connector: connector.key, which, element, side: port.side, toward }]
    })
  })

const portsSpread = (
  routing: Routing,
  connectors: readonly Connector[],
  first: ReadonlyMap<string, RoutedConnector>,
): Map<string, readonly [Choice, Choice]> => {
  const ends = endsOnSides(routing, connectors, first)
  const at = spread(ends)
  const sharing = new Map<string, number>()
  for (const end of ends) {
    const key = `${end.element}\u0000${end.side}`
    sharing.set(key, (sharing.get(key) ?? 0) + 1)
  }
  const alone = new Set(
    ends
      .filter((end) => sharing.get(`${end.element}\u0000${end.side}`) === 1)
      .map((end) => `${end.connector}\u0000${end.which}`),
  )
  const ports = new Map<string, readonly [Choice, Choice]>()
  for (const connector of connectors) {
    const routed = first.get(connector.key)
    if (!routed) continue
    let chosen: [Choice, Choice] = [
      [routed.sourcePort.side, at.get(`${connector.key}\u00000`) ?? routed.sourcePort.at],
      [routed.targetPort.side, at.get(`${connector.key}\u00001`) ?? routed.targetPort.at],
    ]
    if (alone.has(`${connector.key}\u00000`) && alone.has(`${connector.key}\u00001`)) {
      const lined = inLine(extentOf(routing.scene, connector.source), extentOf(routing.scene, connector.target), [
        chosen[0][0],
        chosen[1][0],
      ])
      if (lined) chosen = [[chosen[0][0], lined[0]], [chosen[1][0], lined[1]]]
    }
    ports.set(connector.key, chosen)
  }
  return ports
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
    const made = routing.special(connector)
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
  for (const [key, [source, target]] of portsSpread(routing, searched, first)) {
    const connector = searched.find((one) => one.key === key)
    const before = first.get(key)
    if (!connector || !before) continue
    const routed = routing.searched(connector, [source], [target], false) ?? before
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
