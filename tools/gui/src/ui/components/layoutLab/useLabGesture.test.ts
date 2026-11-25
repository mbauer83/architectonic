// @vitest-environment jsdom
/**
 * The canvas's one gesture, driven through the arranging session: a press without travel only selects,
 * a drag moves (a box carrying its members) or resizes, lines are routed live and again on the drop,
 * and every change is one step undo takes back. Nothing here is mocked but the frame clock.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { LINE_DRAWING, SHAPE_DRAWING } from '../../../domain/layout/lab/__tests__/labDrawingFixtures'
import type { LayoutGeometry } from '../../../domain/schemas/diagramLayoutGeometry'
import { Effect } from 'effect'
import type { ModelService } from '../../../application/ModelService'
import { useArrangementSession } from '../../composables/useArrangementSession'
import { layoutOf } from '../../../domain/layout/arrangementLayout'
import type { Handle } from '../../../domain/layout/lab/labArrangement'
import { type ArrangingAids, useLabGesture } from './useLabGesture'
import { withRouteStated } from '../../../domain/layout/lab/labRouteEdits'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

/** A grouping holding A and B, and C outside it; B relates to C. */
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test',
  name: 'Test',
  canvas: at(0, 0, 600, 400),
  backdrop: [],
  surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] },
  elements: [
    { alias: 'A', key: 'APP@1.a', label: 'A', extent: at(20, 40, 120, 80), inside: 'G', words: [], outside_label: undefined, drawing: SHAPE_DRAWING },
    { alias: 'B', key: 'APP@2.b', label: 'B', extent: at(140, 40, 240, 80), inside: 'G', words: [], outside_label: undefined, drawing: SHAPE_DRAWING },
    { alias: 'C', key: 'APP@3.c', label: 'C', extent: at(400, 40, 500, 80), inside: undefined, words: [], outside_label: undefined, drawing: SHAPE_DRAWING },
  ],
  boxes: [{
    alias: 'G', kind: 'authored-grouping', section: 'boxes', key: 'g-1', label: 'Group',
    extent: at(10, 10, 250, 90), inside: undefined, words: [], title_band: undefined, drawing: SHAPE_DRAWING,
  }],
  relations: [{
    index: 0, key: 'r', source: 'B', target: 'C', decorated: [false, true],
    course: [[240, 60], [400, 60]], label: '', label_size: undefined, drawing: LINE_DRAWING,
  }],
}

/** The one call the session makes of the service while arranging: drawing resized shapes. */
const SERVICE = { drawResizedShapes: () => Effect.succeed([]) } as unknown as ModelService

/** As before snapping and the touching rectangle: nothing snaps, a rectangle selects what it encloses. */
const AS_HINTS: ArrangingAids = { snapping: () => 'hints', rectangle: () => 'encloses' }

const opened = (aids: ArrangingAids = AS_HINTS) => {
  const session = useArrangementSession((shapes) => SERVICE.drawResizedShapes(geometry.artifact_id, shapes))
  session.open(geometry)
  const gesture = useLabGesture(session, ref(null), aids)
  /** The layout the arrangement now states, as Save would write it. */
  const layout = () => {
    const now = session.arrangement.value
    return now ? layoutOf(geometry, now) : null
  }
  return { lab: { ...session, layout }, gesture }
}

/** The pointer pressed on *alias* (or one of its handles) at (x, y): outside an SVG, page and picture agree. */
const down = (x: number, y: number, shiftKey = false) =>
  Object.assign(new MouseEvent('pointerdown', { clientX: x, clientY: y, button: 0, shiftKey }), { pointerId: 1 }) as PointerEvent

const press = (gesture: ReturnType<typeof useLabGesture>, alias: string, x: number, y: number, handle?: Handle) =>
  gesture.press(down(x, y), alias, handle ?? null)

const pointer = (type: string, x: number, y: number) =>
  window.dispatchEvent(new MouseEvent(type, { clientX: x, clientY: y }))

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', (frame: FrameRequestCallback) => { frame(0); return 1 })
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
})
afterEach(() => vi.unstubAllGlobals())

describe('the canvas gesture', () => {
  it('only selects on a press that does not travel', () => {
    const { lab, gesture } = opened()
    press(gesture, 'C', 450, 60)
    pointer('pointermove', 452, 61)
    pointer('pointerup', 452, 61)

    expect(gesture.selected.value).toBe('C')
    expect(lab.history.value).toHaveLength(0)
    expect(lab.routes.value).toBeNull()
    expect(lab.layout()?.elements['APP@3.c']).toEqual({ x: 400, y: 40 })
  })

  it('moves an element by the pointer travel, routing live and keeping the last frame on the drop', () => {
    const { lab, gesture } = opened()
    press(gesture, 'C', 450, 60)
    pointer('pointermove', 470, 100)

    expect(gesture.dragging.value).toBe(true)
    expect(lab.timing.value?.kind).toBe('quick')
    const shown = lab.courses.value.get(0)
    pointer('pointerup', 470, 100)

    expect(gesture.dragging.value).toBe(false)
    expect(lab.courses.value.get(0)).toEqual(shown)
    expect(lab.arrangement.value?.elements.get('C')).toEqual(at(420, 80, 520, 120))
    expect(lab.layout()).toMatchObject({ elements: { 'APP@3.c': { x: 420, y: 80 } } })
    const course = lab.courses.value.get(0)
    expect(course?.at(-1)?.x).toBe(420)

    lab.undo()
    expect(lab.arrangement.value?.elements.get('C')).toEqual(at(400, 40, 500, 80))
    expect(lab.routes.value).toBeNull()
  })

  it('carries a box members with it, and the box with them', () => {
    const { lab, gesture } = opened()
    press(gesture, 'G', 15, 15)
    pointer('pointermove', 15, 65)
    pointer('pointerup', 15, 65)

    expect(lab.layout()).toMatchObject({ elements: { 'APP@1.a': { x: 20, y: 90 }, 'APP@2.b': { x: 140, y: 90 } } })
    expect(lab.placement.value?.boxes.get('G')).toEqual(at(10, 60, 250, 140))
  })

  it('resizes from a handle, never below the smallest element', () => {
    const { lab, gesture } = opened()
    press(gesture, 'C', 500, 80, 'se')
    pointer('pointermove', 560, 100)
    pointer('pointerup', 560, 100)
    expect(lab.layout()).toMatchObject({ elements: { 'APP@3.c': { x: 400, y: 40, w: 160, h: 60 } } })

    press(gesture, 'C', 560, 100, 'se')
    pointer('pointermove', 300, 0)
    pointer('pointerup', 300, 0)
    expect(lab.arrangement.value?.elements.get('C')).toEqual(at(400, 40, 424, 64))
    expect(lab.history.value).toHaveLength(2)
  })

  it('toggles a shape in and out of the selection with Shift, and drags the whole selection', () => {
    const { lab, gesture } = opened()
    press(gesture, 'A', 30, 50)
    pointer('pointerup', 30, 50)
    gesture.press(down(450, 60, true), 'C')
    expect(gesture.selection.value).toEqual(['A', 'C'])
    expect(gesture.selected.value).toBeNull()

    press(gesture, 'C', 450, 60)
    pointer('pointermove', 450, 100)
    pointer('pointerup', 450, 100)
    expect(lab.arrangement.value?.elements.get('A')).toEqual(at(20, 80, 120, 120))
    expect(lab.arrangement.value?.elements.get('C')).toEqual(at(400, 80, 500, 120))
    expect(lab.arrangement.value?.elements.get('B')).toEqual(at(140, 40, 240, 80))
    expect(lab.history.value).toHaveLength(1)

    gesture.press(down(30, 90, true), 'A')
    expect(gesture.selection.value).toEqual(['C'])
  })

  it('selects with a rectangle what it encloses, and a box only when wholly inside it', () => {
    const { gesture } = opened()
    gesture.sweepFrom(down(130, 30))
    pointer('pointermove', 510, 85)
    expect(gesture.rectangle.value).toEqual(at(130, 30, 510, 85))
    pointer('pointerup', 510, 85)
    expect(gesture.selection.value).toEqual(['B', 'C'])
    expect(gesture.rectangle.value).toBeNull()

    gesture.sweepFrom(down(0, 0, true))
    pointer('pointermove', 130, 100)
    pointer('pointerup', 130, 100)
    expect(gesture.selection.value).toEqual(['B', 'C', 'A'])

    gesture.sweepFrom(down(0, 0))
    pointer('pointermove', 260, 100)
    pointer('pointerup', 260, 100)
    expect(gesture.selection.value).toEqual(['A', 'B', 'G'])
  })

  it('selects a box whose body is pressed without travel, and clears on empty paper', () => {
    const { gesture } = opened()
    gesture.sweepFrom(down(200, 85), 'G')
    pointer('pointerup', 200, 85)
    expect(gesture.selected.value).toBe('G')

    gesture.sweepFrom(down(550, 300))
    pointer('pointerup', 550, 300)
    expect(gesture.selection.value).toEqual([])
  })
})

describe('the gesture with the reader’s aids (sketch 02·1, 02·2, 01·5)', () => {
  const SNAPPING: ArrangingAids = { snapping: () => 'snap', rectangle: () => 'touches' }

  it('lands a moved element on the grid, or on a neighbour line with a guide that goes after the drop', () => {
    vi.useFakeTimers()
    const { lab, gesture } = opened(SNAPPING)
    press(gesture, 'C', 450, 60)
    pointer('pointermove', 473, 103)
    expect(gesture.guides.value).toEqual([{ axis: 'y', at: 80, from: 12, to: 532 }])
    pointer('pointerup', 473, 103)
    expect(lab.arrangement.value?.elements.get('C')).toEqual(at(424, 80, 524, 120))
    vi.advanceTimersByTime(699)
    expect(gesture.guides.value).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(gesture.guides.value).toEqual([])
    vi.useRealTimers()
  })

  it('snaps the dragged edge of a resize to a neighbour', () => {
    const { lab, gesture } = opened(SNAPPING)
    press(gesture, 'B', 240, 60, 'e')
    pointer('pointermove', 397, 60)
    pointer('pointerup', 397, 60)
    expect(lab.arrangement.value?.elements.get('B')).toEqual(at(140, 40, 400, 80))
  })

  it('moves a selection together by whole grid steps', () => {
    const { lab, gesture } = opened(SNAPPING)
    press(gesture, 'A', 30, 50)
    pointer('pointerup', 30, 50)
    gesture.press(down(450, 60, true), 'C')
    press(gesture, 'C', 450, 60)
    pointer('pointermove', 455, 71)
    pointer('pointerup', 455, 71)
    expect(lab.arrangement.value?.elements.get('C')).toEqual(at(408, 48, 508, 88))
    expect(gesture.guides.value).toEqual([])
  })

  it('selects what a rectangle touches, by preference', () => {
    const touching = opened(SNAPPING).gesture
    touching.sweepFrom(down(130, 30))
    pointer('pointermove', 300, 60)
    pointer('pointerup', 300, 60)
    expect(touching.selection.value).toEqual(['B'])

    const enclosing = opened().gesture
    enclosing.sweepFrom(down(130, 30))
    pointer('pointermove', 300, 60)
    pointer('pointerup', 300, 60)
    expect(enclosing.selection.value).toEqual([])
  })

  it('picks up the bends a line states inside the rectangle, and carries them with the selection', () => {
    const { lab, gesture } = opened(SNAPPING)
    lab.change((_drawn, now) => withRouteStated(now, 'r', { via: [[320, 60], [320, 150]] }))
    gesture.sweepFrom(down(10, 30))
    pointer('pointermove', 330, 100)
    pointer('pointerup', 330, 100)
    expect(gesture.selection.value).toEqual(['A', 'B'])
    expect(gesture.bends.value).toEqual([{ key: 'r', index: 0 }])

    press(gesture, 'A', 30, 50)
    pointer('pointermove', 30, 66)
    pointer('pointerup', 30, 66)
    expect(lab.arrangement.value?.routes.get('r')?.via?.[0]).toEqual([320, 76])
    expect(lab.arrangement.value?.routes.get('r')?.via?.[1]).toEqual([320, 150])

    gesture.sweepFrom(down(550, 380))
    pointer('pointerup', 550, 380)
    expect(gesture.bends.value).toEqual([])
  })
})
