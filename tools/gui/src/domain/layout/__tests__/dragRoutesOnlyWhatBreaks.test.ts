/**
 * What a drag costs the router on a picture of many lines (A-04.11): a frame routes nothing — the lines
 * of what moved follow it (`followPass`) — and the drop routes only the lines that following leaves
 * breaking a rule they did not break before (`quickPass`). On a 259-element picture every line a drag
 * touched was searched again on every frame, 24–58 ms a move against a 16 ms frame, and a drop that
 * touched a box's lines took seconds.
 *
 * Counted, not timed: the router's search is counted by wrapping it, so the guard holds on any machine.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Extent } from '../geometry'
import { drawnArrangement, moved } from '../canvasArrangement'
import { changedShapes, followPass, fullPass, placementOf, quickPass } from '../canvasRouting'
import type { LayoutGeometry } from '../../schemas/diagramLayoutGeometry'
import { LINE_DRAWING, SHAPE_DRAWING } from './canvasDrawingFixtures'

vi.mock('../routing/search', async (original) => {
  const real = await original<typeof import('../routing/search')>()
  const counted = vi.fn()
  return { ...real, search: (...asked: Parameters<typeof real.search>) => { counted(); return real.search(...asked) }, counted }
})

const searches = (await import('../routing/search') as unknown as { counted: ReturnType<typeof vi.fn> }).counted

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

const element = (alias: string, extent: Extent) => ({
  alias, key: `APP@1.${alias}`, label: alias, extent, inside: undefined, words: [], outside_label: undefined,
  drawing: SHAPE_DRAWING,
})

const line = (index: number, source: string, target: string, course: [number, number][]) => ({
  index, key: `r${index}`, source, target, decorated: [false, true] as [boolean, boolean], course, label: '',
  label_size: undefined, drawing: LINE_DRAWING,
})

/**
 * Three rows of ten elements, each joined to the next in its row by a straight line, as PlantUML drew
 * them: thirty elements and twenty-seven lines.
 */
const ROWS = 3
const COLUMNS = 10
const alias = (row: number, column: number) => `E${row}_${column}`
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 3000, 1000), backdrop: [],
  surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] },
  elements: Array.from({ length: ROWS * COLUMNS }, (_, place) => {
    const [row, column] = [Math.floor(place / COLUMNS), place % COLUMNS]
    return element(alias(row, column), at(column * 300, row * 300, column * 300 + 100, row * 300 + 40))
  }),
  boxes: [],
  relations: Array.from({ length: ROWS * (COLUMNS - 1) }, (_, index) => {
    const [row, column] = [Math.floor(index / (COLUMNS - 1)), index % (COLUMNS - 1)]
    const y = row * 300 + 20
    return line(index, alias(row, column), alias(row, column + 1), [[column * 300 + 100, y], [column * 300 + 300, y]])
  }),
}

const start = drawnArrangement(geometry)
const shown = fullPass(geometry, placementOf(geometry, start))

beforeEach(() => searches.mockClear())
afterEach(() => searches.mockClear())

describe('a drag across a picture of many lines', () => {
  it('takes the picture over routing nothing', () => {
    expect(fullPass(geometry, placementOf(geometry, start)).routes.size).toBe(geometry.relations.length)
    expect(searches).not.toHaveBeenCalled()
  })

  it('routes nothing on a frame: the lines of what moved follow it, every other line stays as shown', () => {
    const before = placementOf(geometry, start)
    const now = placementOf(geometry, moved(geometry, start, alias(1, 4), 30, 60))
    const frame = followPass(geometry, now, new Map(), shown, changedShapes(before, now))

    expect(searches).not.toHaveBeenCalled()
    const into = frame.routes.get(String(9 + 3))!
    expect(into.course.at(-1)).toMatchObject({ x: 4 * 300 + 30 })
    for (const [key, one] of shown.routes) {
      if (key !== String(9 + 3) && key !== String(9 + 4)) expect(frame.routes.get(key)).toBe(one)
    }
  })

  it('routes nothing on a drop whose followed lines break no rule', () => {
    const before = placementOf(geometry, start)
    const now = placementOf(geometry, moved(geometry, start, alias(1, 4), 30, 60))
    const dropped = quickPass(geometry, before, now, new Map(), shown.routes, changedShapes(before, now))

    expect(searches).not.toHaveBeenCalled()
    expect(dropped.routes.get(String(9 + 3))?.course.at(-1)).toMatchObject({ x: 4 * 300 + 30 })
  })

  it('routes on the drop only the line something now stands across', () => {
    const before = placementOf(geometry, start)
    // The element below is lifted onto the line between the two above it.
    const now = placementOf(geometry, moved(geometry, start, alias(1, 5), -150, -300))
    const dropped = quickPass(geometry, before, now, new Map(), shown.routes, changedShapes(before, now))

    expect(searches).toHaveBeenCalled()
    const across = dropped.routes.get(String(4))!
    expect(across.course).not.toEqual(shown.routes.get(String(4))!.course)
    const untouched = [...shown.routes.keys()].filter((key) => !['4', String(9 + 4), String(9 + 5)].includes(key))
    for (const key of untouched) expect(dropped.routes.get(key)?.course).toEqual(shown.routes.get(key)?.course)
  })
})
