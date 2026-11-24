/**
 * Shaping a line by hand states its route: an end slid along its side keeps the bends, the one next to
 * it following; onto another side the bends go and the router takes it round. A segment moved sideways
 * keeps a stub at a port and never shortens a decorated end's run; a jog of a few pixels and a bend in
 * line with both neighbours are tidied away; a label is anchored along its line; a press near a line's
 * end finds the line (Q33).
 */
import { describe, expect, it } from 'vitest'
import type { Extent, Point } from '../../geometry'
import type { Route } from '../../orthogonal'
import { END_RUN } from '../../routeQuality'
import type { RoutedConnector } from '../../routing/scene'
import { drawnArrangement } from '../labArrangement'
import {
  bendsShown, labelAnchoredAt, labelCentre, lineEndNear, portNear, segmentMoved, straightened, tidiedRoute,
  withBendAdded, withBendRemoved, withEndAt, withRouteStated,
} from '../labRouteEdits'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const p = (x: number, y: number): Point => ({ x, y })

const A = at(0, 0, 100, 40)
/** A line out of A's right, down, and into the left of an element further right and below. */
const routed: RoutedConnector = {
  key: '0',
  sourcePort: { side: 'right', at: 0.5 },
  targetPort: { side: 'left', at: 0.5 },
  course: [p(100, 20), p(200, 20), p(200, 120), p(300, 120)],
}

describe('moving an end', () => {
  it('finds the nearest side, clear of the corners, and lines up with the other end when close', () => {
    expect(portNear(A, p(103, 10))).toEqual({ side: 'right', at: 0.25 })
    expect(portNear(A, p(99, -50))).toEqual({ side: 'top', at: 0.96 })
    expect(portNear(A, p(30, 44), p(33, 200), 6)).toEqual({ side: 'bottom', at: 0.33 })
  })

  it('along the same side keeps the bends, the one next to the end following it', () => {
    const route: Route = { from: routed.sourcePort, to: routed.targetPort, via: [[200, 20], [200, 120]] }
    expect(withEndAt(route, 'from', { side: 'right', at: 0.25 }, A).via).toEqual([[200, 10], [200, 120]])
  })

  it('onto another side drops the bends and keeps the other port', () => {
    const route: Route = { from: routed.sourcePort, to: routed.targetPort, via: [[200, 20], [200, 120]] }
    expect(withEndAt(route, 'from', { side: 'bottom', at: 0.5 }, A))
      .toEqual({ from: { side: 'bottom', at: 0.5 }, to: routed.targetPort })
  })
})

describe('bends', () => {
  it('are the stated ones where stated, else the corners the router gave', () => {
    expect(bendsShown(routed.course)).toEqual([p(200, 20), p(200, 120)])
    expect(bendsShown(routed.course, { via: [[150, 20]] })).toEqual([p(150, 20)])
  })

  it('are added in their place along the line, which then states its whole route', () => {
    const added = withBendAdded(routed, p(203, 70))
    expect(added).toEqual({ from: routed.sourcePort, to: routed.targetPort, via: [[200, 20], [200, 70], [200, 120]] })
    expect(withBendRemoved(added, 1).via).toEqual([[200, 20], [200, 120]])
  })

  it('straighten away, the ports and the label kept', () => {
    const route: Route = { from: routed.sourcePort, to: routed.targetPort, via: [[200, 20]], label: { at: 0.5, dx: 0, dy: 4 } }
    expect(straightened(route)).toEqual({ from: routed.sourcePort, to: routed.targetPort, label: route.label })
    expect(withBendRemoved({ ...route, via: [[200, 20]] }, 0)).toEqual(straightened(route))
  })
})

describe('moving a segment', () => {
  it('moves a middle segment sideways, its neighbours following', () => {
    expect(segmentMoved(routed, [false, false], 1, 240)).toEqual([p(100, 20), p(240, 20), p(240, 120), p(300, 120)])
  })

  it('takes a stub at the port when the segment leaves it', () => {
    const course = segmentMoved(routed, [false, false], 0, 50)
    expect(course.slice(0, 4)).toEqual([p(100, 20), p(112, 20), p(112, 50), p(200, 50)])
  })

  it('never shortens a decorated end\'s run below its decoration', () => {
    const course = segmentMoved(routed, [false, true], 1, 290)
    expect(course[2].x).toBe(300 - END_RUN)
  })
})

describe('tidying a reshaped route', () => {
  it('straightens a jog of a few pixels and drops a bend in line with its neighbours', () => {
    const course = [p(100, 20), p(150, 20), p(150, 22), p(200, 22), p(200, 120), p(250, 120), p(300, 120)]
    expect(tidiedRoute(course, routed, 4).via).toEqual([[200, 20], [200, 120]])
  })
})

describe('labels', () => {
  it('are anchored along the line, and drawn back where they were put', () => {
    const anchor = labelAnchoredAt(routed.course, p(210, 70))
    expect(anchor).toEqual({ at: 0.5, dx: 10, dy: 0 })
    expect(labelCentre(routed.course, anchor)).toEqual(p(210, 70))
  })
})

describe('stating a route', () => {
  it('holds an entry only while the route states something', () => {
    const empty = { ...drawnArrangement({ elements: [], boxes: [], relations: [] } as never) }
    const stated = withRouteStated(empty, 'r', { via: [[1, 2]] })
    expect(stated.routes.get('r')).toEqual({ via: [[1, 2]] })
    expect(withRouteStated(stated, 'r', {}).routes.has('r')).toBe(false)
  })
})

describe('a press near a line\'s end', () => {
  it('finds the nearest end within reach, and nothing beyond it', () => {
    const courses = new Map([[0, routed.course], [1, [p(300, 300), p(400, 300)]]])
    expect(lineEndNear(courses, p(298, 118), 6)).toEqual({ line: 0, end: 'to' })
    expect(lineEndNear(courses, p(150, 200), 6)).toBeNull()
  })
})
