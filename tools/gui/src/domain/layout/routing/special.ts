/**
 * The connectors that are not searched, and the route each takes instead.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/special.py`: one from an element to
 * itself loops round its corner; one between a box and an element inside it runs straight from the
 * part to the whole's border; one between two elements closer than a stub is joined the most direct way.
 */
import { endsConflict, formedAfresh, fraction } from '../attachment'
import type { Extent, Point } from '../geometry'
import { encloses, heightOf, widthOf } from '../geometry'
import type { Port, Side } from '../orthogonal'
import { courseOf, leavesLevel } from '../orthogonal'
import { stubOf } from './ports'
import type { Connector, RoutedConnector, RoutingScene } from './scene'
import { SIDES, extentOf, runFor } from './scene'
import type { Visibility } from './visibility'

const shareAlong = (extent: Extent, coordinate: number, level: boolean): number => {
  const length = level ? heightOf(extent) : widthOf(extent)
  return length > 0 ? (coordinate - (level ? extent.top : extent.left)) / length : 0.5
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

const wholeToPart = (
  visibility: Visibility,
  connector: Connector,
  source: Extent,
  target: Extent,
  own: readonly Extent[],
): RoutedConnector | null => {
  const wholeIsSource = encloses(source, target)
  const whole = wholeIsSource ? source : target
  const part = wholeIsSource ? target : source
  const partKey = wholeIsSource ? connector.target : connector.source
  const passage = visibility.passage([partKey, partKey])
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
    if (passage.stepBlocked(stub.at, border, own)) continue
    const level = leavesLevel(side)
    const wholePort: Port = { side, at: fraction(shareAlong(whole, level ? border.y : border.x, level)) }
    return wholeIsSource
      ? { key: connector.key, sourcePort: wholePort, targetPort: stub.port, course: [border, stub.at] }
      : { key: connector.key, sourcePort: stub.port, targetPort: wholePort, course: [stub.at, border] }
  }
  return null
}

/** The route of a connector that is not searched; true where it is to be searched. */
export const special = (
  scene: RoutingScene,
  visibility: Visibility,
  connector: Connector,
  own: readonly Extent[],
): RoutedConnector | null | true => {
  const source = extentOf(scene, connector.source)
  const target = extentOf(scene, connector.target)
  if (connector.source === connector.target) return aroundItself(connector, source)
  if (encloses(source, target) || encloses(target, source)) {
    return wholeToPart(visibility, connector, source, target, own)
  }
  if (endsConflict(source, target)) {
    const made = formedAfresh({}, source, target)
    const course = courseOf(made, source, target)
    if (made.from && made.to && course) {
      return { key: connector.key, sourcePort: made.from, targetPort: made.to, course }
    }
  }
  return true
}
