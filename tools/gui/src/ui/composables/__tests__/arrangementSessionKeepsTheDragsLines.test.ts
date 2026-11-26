/**
 * A drop keeps the picture the drag showed (owner's defect): each drag frame runs the router's quick
 * pass, and the release used to run the full pass over every line, which chose other sides and ports —
 * the lines jumped as the mouse was released. Now the released picture is the last frame, routed at
 * once if it was still waiting, and undo and redo show each state with the lines it was shown with.
 *
 * The scene is one where the two passes disagree: A is dragged from beside B to below it, and the
 * quick pass keeps the sides the line left and entered by while the full pass would turn it.
 */
import { Effect } from 'effect'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Extent, Point } from '../../../domain/layout/geometry'
import { moved } from '../../../domain/layout/canvasArrangement'
import { breachesOf, countByTier } from '../../../domain/layout/canvasBreaches'
import { changedShapes, fullPass, textRegions } from '../../../domain/layout/canvasRouting'
import { LINE_DRAWING, SHAPE_DRAWING } from '../../../domain/layout/__tests__/canvasDrawingFixtures'
import type { LayoutGeometry } from '../../../domain/schemas/diagramLayoutGeometry'
import { useArrangementSession } from '../useArrangementSession'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

const element = (alias: string, extent: Extent) => ({
  alias, key: `APP@1.${alias}`, label: alias, extent, inside: undefined, words: [], outside_label: undefined,
  drawing: SHAPE_DRAWING,
})

const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 800, 600), backdrop: [],
  surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] },
  elements: [element('A', at(20, 100, 120, 140)), element('B', at(400, 100, 500, 140))],
  boxes: [],
  relations: [{
    index: 0, key: 'r', source: 'A', target: 'B', decorated: [false, true],
    course: [[120, 120], [400, 120]], label: '', label_size: undefined, drawing: LINE_DRAWING,
  }],
}

let frames: FrameRequestCallback[] = []
const flush = () => { const now = frames; frames = []; now.forEach((frame) => frame(0)) }

beforeEach(() => {
  frames = []
  vi.stubGlobal('requestAnimationFrame', (frame: FrameRequestCallback) => { frames.push(frame); return frames.length })
  vi.stubGlobal('cancelAnimationFrame', () => { frames = [] })
})
afterEach(() => vi.unstubAllGlobals())

const opened = () => {
  const session = useArrangementSession(() => Effect.succeed([]))
  session.open(geometry)
  return session
}

type Session = ReturnType<typeof opened>

const courseNow = (session: Session): readonly Point[] => session.courses.value.get(0) ?? []

/** Drag A by (dx, dy) in *steps* frames, each drawn; the last offset is previewed but its frame not drawn. */
const drag = (session: Session, dx: number, dy: number, steps: number, drawLast: boolean) => {
  session.begin()
  const start = session.arrangement.value
  const startPlacement = session.placement.value
  if (!start || !startPlacement) throw new Error('nothing open')
  for (let step = 1; step <= steps; step += 1) {
    const next = moved(geometry, start, 'A', Math.round(dx * step / steps), Math.round(dy * step / steps))
    session.preview(next, changedShapes(startPlacement, { ...startPlacement, elements: next.elements }))
    if (step < steps || drawLast) flush()
  }
}

describe('a drop keeps the lines the drag showed', () => {
  it('releases on the picture of the last frame, where the full pass would have turned the line', () => {
    const session = opened()
    drag(session, 380, 260, 12, true)
    const shown = courseNow(session)
    const where = session.placement.value
    if (!where) throw new Error('nothing placed')
    // The scene is one the two passes disagree on, or this test would prove nothing.
    expect(fullPass(geometry, where).routes.get('0')?.course).not.toEqual(shown)

    session.commit()
    expect(courseNow(session)).toEqual(shown)
    const breaches = breachesOf(geometry, where, session.courses.value, textRegions(geometry, where))
    expect(countByTier(breaches).hard).toBe(0)
  })

  it('routes a frame still waiting at the release, rather than dropping it or routing everything afresh', () => {
    const session = opened()
    drag(session, 380, 260, 12, false)
    const before = courseNow(session)
    session.commit()
    const released = courseNow(session)
    expect(released).not.toEqual(before)
    expect(released[0].y).toBeGreaterThan(300)
  })

  it('shows each state again with the lines it was shown with, on undo and on redo', () => {
    const session = opened()
    const automatic = courseNow(session)
    drag(session, 380, 260, 12, true)
    session.commit()
    const released = courseNow(session)

    session.undo()
    expect(courseNow(session)).toEqual(automatic)
    session.redo()
    expect(courseNow(session)).toEqual(released)
  })
})
