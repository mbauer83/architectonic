/**
 * Which port each end of a searched connector takes, once every connector has a first route.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/spreading.py`: ends sharing a side are
 * spread along it; a connector whose two ends each have their side to themselves is lined up to run
 * straight where its elements overlap across; a stated port stays as stated. A port whose stub runs
 * into another connector's is moved along its side by the ideal separation.
 */
import { centreOf } from '../geometry'
import { leavesLevel } from '../orthogonal'
import { LINE_CLEARANCE } from '../routeQuality'
import type { EndOnSide, Stub } from './ports'
import { inLine, spread, stubOf } from './ports'
import type { Choice, Connector, RoutedConnector, RoutingScene } from './scene'
import { IDEAL_SEPARATION, byText, extentOf, runFor } from './scene'

const endsOnSides = (
  scene: RoutingScene,
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
      const centre = centreOf(extentOf(scene, other))
      const toward = leavesLevel(port.side) ? centre.y : centre.x
      return [{ connector: connector.key, which, element, side: port.side, toward }]
    })
  })

/** The port each end of *connectors* takes, by connector key, given the sides of its *first* route. */
export const portsSpread = (
  scene: RoutingScene,
  connectors: readonly Connector[],
  first: ReadonlyMap<string, RoutedConnector>,
): Map<string, readonly [Choice, Choice]> => {
  const ends = endsOnSides(scene, connectors, first)
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
      const lined = inLine(extentOf(scene, connector.source), extentOf(scene, connector.target), [
        chosen[0][0],
        chosen[1][0],
      ])
      if (lined) chosen = [[chosen[0][0], lined[0]], [chosen[1][0], lined[1]]]
    }
    ports.set(connector.key, chosen)
  }
  return clearOfFacing(scene, connectors, ports)
}

const stubFor = (scene: RoutingScene, connector: Connector, which: number, [side, at]: Choice): Stub =>
  stubOf(
    extentOf(scene, which === 0 ? connector.source : connector.target),
    side,
    at,
    runFor(connector.decorated[which]),
  )

/** Whether two stubs lie along each other closer than the least separation. */
const meet = (one: Stub, other: Stub): boolean => {
  const level = one.at.y === one.end.y
  if (level !== (other.at.y === other.end.y)) return false
  const at = level ? one.at.y : one.at.x
  const otherAt = level ? other.at.y : other.at.x
  const span = (stub: Stub): [number, number] => {
    const [a, b] = level ? [stub.at.x, stub.end.x] : [stub.at.y, stub.end.y]
    return [Math.min(a, b), Math.max(a, b)]
  }
  const [low, high] = span(one)
  const [otherLow, otherHigh] = span(other)
  return Math.abs(at - otherAt) < LINE_CLEARANCE + 1 && Math.min(high, otherHigh) - Math.max(low, otherLow) > 0
}

/** *ports* with each unstated port whose stub runs into another connector's moved along its side. */
const clearOfFacing = (
  scene: RoutingScene,
  connectors: readonly Connector[],
  ports: Map<string, readonly [Choice, Choice]>,
): Map<string, readonly [Choice, Choice]> => {
  const ends = [...connectors]
    .sort((one, other) => byText(one.key, other.key))
    .filter((connector) => ports.has(connector.key))
    .flatMap((connector) => [0, 1].map((which) => [connector, which] as const))
  ends.forEach(([connector, which], position) => {
    if ((which === 0 ? connector.sourcePort : connector.targetPort) !== undefined) return
    const chosen = ports.get(connector.key) as readonly [Choice, Choice]
    const [side, at] = chosen[which]
    const extent = extentOf(scene, which === 0 ? connector.source : connector.target)
    const length = leavesLevel(side) ? extent.bottom - extent.top : extent.right - extent.left
    const others = ends
      .slice(0, position)
      .filter(([other]) => other.key !== connector.key)
      .map(([other, otherWhich]) => {
        const theirs = ports.get(other.key) as readonly [Choice, Choice]
        return stubFor(scene, other, otherWhich, theirs[otherWhich])
      })
    if (others.length === 0 || !others.some((one) => meet(stubFor(scene, connector, which, [side, at]), one))) return
    for (const shift of [IDEAL_SEPARATION, -IDEAL_SEPARATION, 2 * IDEAL_SEPARATION, -2 * IDEAL_SEPARATION]) {
      const moved = length > 0 ? at + shift / length : at
      const stub = stubFor(scene, connector, which, [side, moved])
      if (moved > 0 && moved < 1 && !others.some((one) => meet(stub, one))) {
        const next: [Choice, Choice] = [chosen[0], chosen[1]]
        next[which] = [side, moved]
        ports.set(connector.key, next)
        break
      }
    }
  })
  return ports
}
