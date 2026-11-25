// @vitest-environment jsdom
/**
 * The canvas places the title and the legend by asking the server, never by a rule of its own: it sends
 * where the diagram is now — the surround as the geometry read handed it over, the shapes, the courses and
 * the labels — once the picture settles, and draws each part moved by the answer. A picture PlantUML still
 * arranges asks nothing; an older answer is not drawn over a newer one.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Effect } from 'effect'
import type { Extent } from '../../../domain/layout/geometry'
import { LINE_DRAWING, SHAPE_DRAWING } from '../../../domain/layout/lab/__tests__/labDrawingFixtures'
import type { LayoutGeometry } from '../../../domain/schemas/diagramLayoutGeometry'
import type { SurroundPlacement } from '../../../ports/DiagramLayoutRepository'
import { useArrangementSession } from '../useArrangementSession'
import { placementOf, useSurroundPlacement } from '../useSurroundPlacement'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const NODE = { tag: 'g', attributes: {}, children: [] }

const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 600, 400), backdrop: [],
  surround: { drawn: at(20, 40, 500, 280), parts: [{ drawing: NODE, extent: at(200, 5, 300, 20) }] },
  elements: [
    { alias: 'A', key: 'APP@1.a', label: 'A', extent: at(20, 40, 120, 80), words: [], drawing: SHAPE_DRAWING },
    { alias: 'C', key: 'APP@3.c', label: 'C', extent: at(400, 240, 500, 280), words: [], drawing: SHAPE_DRAWING },
  ],
  boxes: [],
  relations: [{
    index: 0, key: 'r', source: 'A', target: 'C', decorated: [false, true],
    course: [[120, 60], [400, 260]], label: 'uses', label_size: [30, 10], drawing: LINE_DRAWING,
  }],
}

const opened = (answers: (placement: SurroundPlacement) => readonly (readonly [number, number])[]) => {
  const session = useArrangementSession(() => Effect.succeed([]), (_drawn, automatic) => automatic)
  const place = vi.fn((placement: SurroundPlacement) => Effect.succeed(answers(placement)))
  const placed = useSurroundPlacement(session, place)
  session.open(geometry)
  return { session, place, placed }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('requestAnimationFrame', (frame: FrameRequestCallback) => { frame(0); return 1 })
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('the title and the legend of a diagram being arranged', () => {
  it('stay where PlantUML drew them, asking nothing, while PlantUML arranges the picture', async () => {
    const { place, placed } = opened(() => [[9, 9]])
    await vi.runAllTimersAsync()
    expect(place).not.toHaveBeenCalled()
    expect(placed.value.map((part) => part.by)).toEqual([{ x: 0, y: 0 }])
  })

  it('are placed by the server from where the diagram is now, once it settles', async () => {
    const { session, place, placed } = opened(() => [[40, 0]])
    session.change((_drawn, now) => ({ ...now, elements: new Map([...now.elements, ['C', at(440, 240, 540, 280)]]) }))
    await vi.runAllTimersAsync()

    expect(place).toHaveBeenCalled()
    const asked = place.mock.calls.at(-1)?.[0]
    expect(asked?.drawn).toEqual(geometry.surround.drawn)
    expect(asked?.parts).toEqual([at(200, 5, 300, 20)])
    expect(asked?.shapes).toContainEqual(at(440, 240, 540, 280))
    expect(asked?.labels).toHaveLength(1)
    expect(placed.value[0]).toMatchObject({ by: { x: 40, y: 0 }, extent: at(240, 5, 340, 20) })
  })

  it('send the same placement the session holds', () => {
    const { session } = opened(() => [])
    session.change((_drawn, now) => now)
    const placement = placementOf(session)
    expect(placement?.courses.length).toBe(1)
    expect(placement?.shapes).toHaveLength(2)
  })
})
