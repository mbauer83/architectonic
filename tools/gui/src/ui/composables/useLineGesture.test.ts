// @vitest-environment jsdom
/**
 * The canvas's line gestures, driven through a real arranging session: a press selects a line, or
 * picks it where it ends on an element's edge (Q33); an end, a segment, a bend and the label are
 * dragged, each one step that states the line's route; a double press adds and removes a bend, as
 * Delete does a picked one. Nothing here is mocked but the frame clock.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { Effect } from 'effect'
import type { Extent } from '../../domain/layout/geometry'
import { LINE_DRAWING, SHAPE_DRAWING } from '../../domain/layout/__tests__/canvasDrawingFixtures'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import { useArrangementSession } from './useArrangementSession'
import { useLineGesture } from './useLineGesture'
import { labelCentre } from '../../domain/layout/canvasRouteEdits'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const element = (alias: string, extent: Extent) => ({
  alias, key: `APP@1.${alias}`, label: alias, extent, inside: undefined, words: [], outside_label: undefined,
  drawing: SHAPE_DRAWING,
})

/** A beside and above C: the line from A to C turns twice, its last run as short as its arrowhead allows. */
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 700, 500), backdrop: [],
  surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] },
  elements: [element('A', at(20, 40, 120, 80)), element('C', at(400, 240, 500, 280))],
  boxes: [],
  relations: [{
    index: 0, key: 'r', source: 'A', target: 'C', decorated: [false, true],
    course: [[120, 60], [370, 60], [370, 260], [400, 260]], label: '', label_size: undefined, drawing: LINE_DRAWING,
  }],
}

const event = (type: string, x: number, y: number) =>
  Object.assign(new MouseEvent(type, { clientX: x, clientY: y, button: 0, bubbles: true }), { pointerId: 1 }) as PointerEvent
const pointer = (type: string, x: number, y: number) => window.dispatchEvent(event(type, x, y))

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', (frame: FrameRequestCallback) => { frame(0); return 1 })
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
})
afterEach(() => vi.unstubAllGlobals())

const opened = () => {
  const session = useArrangementSession(() => Effect.succeed([]))
  session.open(geometry)
  session.change((_drawn, now) => now)
  const picked = vi.fn()
  const lines = useLineGesture(session, ref(null), ref(1), picked)
  return { session, lines, picked }
}

const course = (session: ReturnType<typeof opened>['session']) => session.courses.value.get(0) ?? []
const stated = (session: ReturnType<typeof opened>['session']) => session.arrangement.value?.routes.get('r')

describe('the line gestures', () => {
  it('select a line on a press, letting go of the shapes', () => {
    const { lines, picked } = opened()
    lines.pressLine(event('pointerdown', 0, 0), 0)
    expect(lines.line.value).toBe(0)
    expect(picked).toHaveBeenCalled()
    expect(lines.bends.value.length).toBeGreaterThan(0)
    lines.clear()
    expect(lines.line.value).toBeNull()
  })

  it('pick a line where it ends on an element\'s edge, and drag that end round onto another side (Q33)', () => {
    const { session, lines } = opened()
    const [start] = course(session)
    expect(lines.pressNearAnEnd(event('pointerdown', start.x + 2, start.y + 1))).toBe(true)
    expect(lines.line.value).toBe(0)
    pointer('pointermove', 70, 85)
    pointer('pointerup', 70, 85)
    expect(stated(session)?.from?.side).toBe('bottom')
    expect(course(session)[0]).toEqual({ x: 70, y: 80 })
    session.undo()
    expect(stated(session)).toBeUndefined()
    expect(lines.pressNearAnEnd(event('pointerdown', 300, 400))).toBe(false)
  })

  it('move a segment sideways, stating the whole route, as one step; never into an arrowhead\'s run', () => {
    const { session, lines } = opened()
    lines.pressLine(event('pointerdown', 0, 0), 0)
    const before = course(session)
    const middle = before.findIndex((point, index) => index > 0 && Math.abs(point.x - before[index - 1].x) < 0.5)
    lines.pressSegment(event('pointerdown', before[middle].x, before[middle].y), middle - 1)
    pointer('pointermove', before[middle].x - 40, before[middle].y)
    pointer('pointerup', before[middle].x - 40, before[middle].y)
    expect(stated(session)?.via?.some(([x]) => x === before[middle].x - 40)).toBe(true)
    expect(session.history.value.length).toBe(2)
    // Towards the decorated target its run stops the segment a decoration's run short of the port.
    lines.pressSegment(event('pointerdown', before[middle].x - 40, before[middle].y), middle - 1)
    pointer('pointermove', before[middle].x + 60, before[middle].y)
    pointer('pointerup', before[middle].x + 60, before[middle].y)
    expect(Math.max(...(stated(session)?.via ?? []).map(([x]) => x))).toBe(before[middle].x)
  })

  it('add a bend on a double press, move it, and remove it by Delete or a double press', () => {
    const { session, lines } = opened()
    lines.pressLine(event('pointerdown', 0, 0), 0)
    const corners = lines.bends.value.length
    const [a, b] = course(session)
    lines.doublePress(new MouseEvent('dblclick', { clientX: (a.x + b.x) / 2, clientY: a.y }))
    expect(lines.bends.value.length).toBe(corners + 1)

    lines.pressBend(event('pointerdown', lines.bends.value[0].x, lines.bends.value[0].y), 0)
    expect(lines.bend.value).toBe(0)
    pointer('pointermove', lines.bends.value[0].x, lines.bends.value[0].y + 30)
    pointer('pointerup', lines.bends.value[0].x, lines.bends.value[0].y + 30)
    expect(stated(session)?.via?.length).toBeGreaterThan(0)

    lines.pressBend(event('pointerdown', 0, 0), 0)
    pointer('pointerup', 0, 0)
    expect(lines.removePickedBend()).toBe(true)
    expect(lines.removePickedBend()).toBe(false)
    const left = lines.bends.value.length
    lines.doublePress(new MouseEvent('dblclick'), 0)
    expect(lines.bends.value.length).toBeLessThanOrEqual(left)
  })

  it('move the label along its line, anchored there, without re-routing the line', () => {
    const { session, lines } = opened()
    const before = course(session)
    lines.pressLabel(event('pointerdown', 0, 0), 0)
    expect(lines.line.value).toBe(0)
    pointer('pointermove', 30, 20)
    expect(lines.movingLabel.value).toBe(true)
    pointer('pointerup', 30, 20)
    expect(lines.movingLabel.value).toBe(false)
    expect(stated(session)?.label).toBeDefined()
    expect(course(session)).toEqual(before)
  })

  it('nudge a picked label by the arrows, as one step, and only while the label is the one picked (02·5)', () => {
    const { session, lines } = opened()
    lines.pressLabel(event('pointerdown', 0, 0), 0)
    pointer('pointerup', 0, 0)
    expect(lines.labelPicked.value).toBe(true)
    const steps = session.history.value.length
    expect(lines.nudgeLabel(2, 0)).toBe(true)
    expect(stated(session)?.label).toBeDefined()
    expect(session.history.value.length).toBe(steps + 1)
    lines.pressLine(event('pointerdown', 0, 0), 0)
    expect(lines.nudgeLabel(2, 0)).toBe(false)
  })

  it('nudge a picked label by screen pixels, whatever the zoom: 2 px shown at 50% is 4 on the picture (A-02.15)', () => {
    const session = useArrangementSession(() => Effect.succeed([]))
    session.open(geometry)
    session.change((_drawn, now) => now)
    const lines = useLineGesture(session, ref(null), ref(2), vi.fn())
    lines.pressLabel(event('pointerdown', 0, 0), 0)
    pointer('pointerup', 0, 0)
    const centre = () => {
      const anchor = stated(session)?.label ?? { at: 0.5, dx: 0, dy: 0 }
      const along = course(session)
      return labelCentre(along, anchor)
    }
    const before = centre()
    lines.nudgeLabel(0, 2)
    expect(centre().y - before.y).toBeCloseTo(4, 0)
    expect(centre().x - before.x).toBeCloseTo(0, 0)
  })
})
