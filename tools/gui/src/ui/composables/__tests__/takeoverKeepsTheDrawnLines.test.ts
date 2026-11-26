/**
 * Taking a picture over keeps PlantUML's lines (owner, 2026-11-25, A-04.11): the first move routes only
 * the lines touching what moved, so it costs what one line costs however large the picture. Taking over
 * routed every line afresh, and widened the picture first, which on a 259-element view took minutes.
 *
 * The lines here are drawn as no router would draw them — a detour over the top — so a line routed
 * afresh is told from a line kept.
 */
import { Effect } from 'effect'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Extent, Point } from '../../../domain/layout/geometry'
import { drawnArrangement, moved } from '../../../domain/layout/lab/labArrangement'
import { fullPass, placementOf } from '../../../domain/layout/lab/labRouting'
import { LINE_DRAWING, SHAPE_DRAWING } from '../../../domain/layout/lab/__tests__/labDrawingFixtures'
import type { LayoutGeometry } from '../../../domain/schemas/diagramLayoutGeometry'
import { pointsOf } from '../../../domain/schemas/diagramLayoutGeometry'
import { useArrangementSession } from '../useArrangementSession'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

const element = (alias: string, extent: Extent) => ({
  alias, key: `APP@1.${alias}`, label: alias, extent, inside: undefined, words: [], outside_label: undefined,
  drawing: SHAPE_DRAWING,
})

const line = (index: number, source: string, target: string, course: [number, number][]) => ({
  index, key: `r${index}`, source, target, decorated: [false, true] as [boolean, boolean], course, label: '',
  label_size: undefined, drawing: LINE_DRAWING,
})

/** A, B and C in a row; A to B and B to C each drawn over the top, as PlantUML may. */
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 900, 400), backdrop: [],
  surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] },
  elements: [element('A', at(20, 200, 120, 240)), element('B', at(320, 200, 420, 240)),
    element('C', at(620, 200, 720, 240))],
  boxes: [],
  relations: [
    line(0, 'A', 'B', [[70, 200], [70, 100], [370, 100], [370, 200]]),
    line(1, 'B', 'C', [[390, 200], [390, 60], [670, 60], [670, 200]]),
  ],
}

const drawn = (index: number): Point[] => pointsOf(geometry.relations[index].course)

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', (frame: FrameRequestCallback) => { frame(0); return 1 })
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
})
afterEach(() => vi.unstubAllGlobals())

describe('taking a picture over', () => {
  it('keeps every line PlantUML drew, and moves nothing', () => {
    const session = useArrangementSession(() => Effect.succeed([]))
    session.open(geometry)
    session.begin()
    expect(session.state.value?.byHand).toBe(true)
    expect(session.arrangement.value?.elements).toEqual(drawnArrangement(geometry).elements)
    expect(session.courses.value.get(0)).toEqual(drawn(0))
    expect(session.courses.value.get(1)).toEqual(drawn(1))
  })

  it('routes only the lines of what the first move moved', () => {
    const session = useArrangementSession(() => Effect.succeed([]))
    session.open(geometry)
    session.change((picture, now) => moved(picture, now, 'C', 0, 100))
    expect(session.courses.value.get(0)).toEqual(drawn(0))
    expect(session.courses.value.get(1)).not.toEqual(drawn(1))
    session.undo()
    expect(session.state.value?.byHand).toBe(false)
  })
})

describe('a stored layout opened', () => {
  it('draws PlantUML\'s line wherever nothing that moved touches it, as the composer does', () => {
    const where = placementOf(geometry, moved(geometry, drawnArrangement(geometry), 'C', 0, 100))
    const routes = fullPass(geometry, where).routes
    expect(routes.get('0')?.course).toEqual(drawn(0))
    expect(routes.get('1')?.course).not.toEqual(drawn(1))
  })

  it('routes a line the moved element now stands on, though neither of its ends moved', () => {
    const where = placementOf(geometry, moved(geometry, drawnArrangement(geometry), 'C', -480, -120))
    expect(fullPass(geometry, where).routes.get('0')?.course).not.toEqual(drawn(0))
  })
})
