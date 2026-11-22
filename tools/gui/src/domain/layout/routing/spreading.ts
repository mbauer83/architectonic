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
import { Lines } from './lines'
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

const meetsEarlier = (stub: Stub, earlier: Lines): boolean => {
  const [a, b] = stub.at.y === stub.end.y ? [stub.at.x, stub.end.x] : [stub.at.y, stub.end.y]
  return earlier.spansNear(stub.at, stub.end, LINE_CLEARANCE + 1).some(
    ([, low, high]) => Math.min(Math.max(a, b), high) > Math.max(Math.min(a, b), low),
  )
}

/** Keep both stubs of each connector clear of previously placed connectors. */
const clearOfFacing = (
  scene: RoutingScene,
  connectors: readonly Connector[],
  ports: Map<string, readonly [Choice, Choice]>,
): Map<string, readonly [Choice, Choice]> => {
  const earlier = new Lines()
  for (const connector of [...connectors].sort((a, b) => byText(a.key, b.key))) {
    const initial = ports.get(connector.key)
    if (!initial) continue
    const chosen: [Choice, Choice] = [...initial]
    const placed: Stub[] = []
    chosen.forEach(([side, at], which) => {
      let stub = stubFor(scene, connector, which, [side, at])
      const stated = which === 0 ? connector.sourcePort : connector.targetPort
      if (stated === undefined && meetsEarlier(stub, earlier)) {
        const extent = extentOf(scene, which === 0 ? connector.source : connector.target)
        const length = leavesLevel(side) ? extent.bottom - extent.top : extent.right - extent.left
        for (const shift of [1, -1, 2, -2]) {
          const moved = length > 0 ? at + shift * IDEAL_SEPARATION / length : at
          const trial = stubFor(scene, connector, which, [side, moved])
          if (moved > 0 && moved < 1 && !meetsEarlier(trial, earlier)) {
            chosen[which] = [side, moved]
            stub = trial
            break
          }
        }
      }
      placed.push(stub)
    })
    ports.set(connector.key, chosen)
    for (const stub of placed) earlier.add(stub.at, stub.end)
  }
  return ports
}
