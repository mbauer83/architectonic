// @vitest-environment jsdom
/**
 * The lab's one gesture, driven through the lab's own session: a press without travel only selects,
 * a drag moves (a box carrying its members) or resizes, lines are routed live and again on the drop,
 * and every change is one step undo takes back. Nothing here is mocked but the frame clock.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { drawnArrangement } from '../../../domain/layout/lab/labArrangement'
import { LINE_DRAWING, SHAPE_DRAWING } from '../../../domain/layout/lab/__tests__/labDrawingFixtures'
import type { LabGeometry } from '../../../domain/layout/lab/labGeometry'
import { useLayoutLab } from '../../composables/useLayoutLab'
import type { Handle } from '../../../domain/layout/lab/labArrangement'
import { useLabGesture } from './useLabGesture'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

/** A grouping holding A and B, and C outside it; B relates to C. */
const geometry: LabGeometry = {
  artifact_id: 'ARC@1.a.test',
  name: 'Test',
  canvas: at(0, 0, 600, 400),
  backdrop: [],
  elements: [
    { alias: 'A', key: 'APP@1.a', label: 'A', extent: at(20, 40, 120, 80), inside: 'G', words: [], outside_label: null, drawing: SHAPE_DRAWING },
    { alias: 'B', key: 'APP@2.b', label: 'B', extent: at(140, 40, 240, 80), inside: 'G', words: [], outside_label: null, drawing: SHAPE_DRAWING },
    { alias: 'C', key: 'APP@3.c', label: 'C', extent: at(400, 40, 500, 80), inside: null, words: [], outside_label: null, drawing: SHAPE_DRAWING },
  ],
  boxes: [{
    alias: 'G', kind: 'authored-grouping', section: 'boxes', key: 'g-1', label: 'Group',
    extent: at(10, 10, 250, 90), inside: null, words: [], title_band: null, drawing: SHAPE_DRAWING,
  }],
  relations: [{
    index: 0, key: 'r', source: 'B', target: 'C', decorated: [false, true],
    course: [[240, 60], [400, 60]], label: '', label_size: null, drawing: LINE_DRAWING,
  }],
}

const opened = () => {
  const lab = useLayoutLab()
  lab.geometry.value = geometry
  lab.arrangement.value = drawnArrangement(geometry)
  const gesture = useLabGesture(lab, ref(null))
  return { lab, gesture }
}

/** The pointer pressed on *alias* (or one of its handles) at (x, y): outside an SVG, page and picture agree. */
const press = (gesture: ReturnType<typeof useLabGesture>, alias: string, x: number, y: number, handle?: Handle) =>
  gesture.press(
    Object.assign(new MouseEvent('pointerdown', { clientX: x, clientY: y, button: 0 }), { pointerId: 1 }) as PointerEvent,
    alias,
    handle ?? null,
  )

const pointer = (type: string, x: number, y: number) =>
  window.dispatchEvent(new MouseEvent(type, { clientX: x, clientY: y }))

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', (frame: FrameRequestCallback) => { frame(0); return 1 })
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
})
afterEach(() => vi.unstubAllGlobals())

describe('the layout lab gesture', () => {
  it('only selects on a press that does not travel', () => {
    const { lab, gesture } = opened()
    press(gesture, 'C', 450, 60)
    pointer('pointermove', 452, 61)
    pointer('pointerup', 452, 61)

    expect(gesture.selected.value).toBe('C')
    expect(lab.history.value).toHaveLength(0)
    expect(lab.routes.value).toBeNull()
    expect(lab.layout.value).toEqual({})
  })

  it('moves an element by the pointer travel, routing live and again on the drop', () => {
    const { lab, gesture } = opened()
    press(gesture, 'C', 450, 60)
    pointer('pointermove', 470, 100)

    expect(gesture.dragging.value).toBe(true)
    expect(lab.timing.value?.kind).toBe('quick')
    pointer('pointerup', 470, 100)

    expect(gesture.dragging.value).toBe(false)
    expect(lab.timing.value?.kind).toBe('full')
    expect(lab.arrangement.value?.elements.get('C')).toEqual(at(420, 80, 520, 120))
    expect(lab.layout.value).toEqual({ elements: { 'APP@3.c': { x: 420, y: 80 } } })
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

    expect(lab.layout.value).toEqual({ elements: { 'APP@1.a': { x: 20, y: 90 }, 'APP@2.b': { x: 140, y: 90 } } })
    expect(lab.placement.value?.boxes.get('G')).toEqual(at(10, 60, 250, 140))
  })

  it('resizes from a handle, never below the smallest element', () => {
    const { lab, gesture } = opened()
    press(gesture, 'C', 500, 80, 'se')
    pointer('pointermove', 560, 100)
    pointer('pointerup', 560, 100)
    expect(lab.layout.value).toEqual({ elements: { 'APP@3.c': { x: 400, y: 40, w: 160, h: 60 } } })

    press(gesture, 'C', 560, 100, 'se')
    pointer('pointermove', 300, 0)
    pointer('pointerup', 300, 0)
    expect(lab.arrangement.value?.elements.get('C')).toEqual(at(400, 40, 424, 64))
    expect(lab.history.value).toHaveLength(2)
  })

  it('widens as one step, and reset returns PlantUML arrangement and lines', () => {
    const { lab } = opened()
    lab.widen()
    expect(lab.history.value).toHaveLength(1)
    expect(lab.routes.value).not.toBeNull()
    expect(lab.counts.value.hard).toBe(0)

    lab.reset()
    expect(lab.history.value).toHaveLength(0)
    expect(lab.routes.value).toBeNull()
    expect(lab.layout.value).toEqual({})
    expect(lab.courses.value.get(0)).toEqual([{ x: 240, y: 60 }, { x: 400, y: 60 }])
  })
})
