/**
 * An arrangement written down and read back agree; the patch between two layouts changes only what
 * differs, each entry checked against what was read; and an edit counts what it arranged, a box moved
 * with its contents being one change.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../geometry'
import type { LayoutGeometry } from '../../schemas/diagramLayoutGeometry'
import {
  arrangedBy, arrangedUnits, layoutOf, layoutPatchBetween, patchIsEmpty, shapedLines, shownRoutesOfMoved,
} from '../arrangementLayout'
import type { RoutedConnector } from '../routing/scene'
import { drawnArrangement, moved, resized } from '../canvasArrangement'
import { placementOf } from '../canvasRouting'
import { LINE_DRAWING, SHAPE_DRAWING } from './canvasDrawingFixtures'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

const element = (alias: string, key: string, extent: Extent, inside?: string) => ({
  alias, key, label: alias, extent, inside, words: [], outside_label: undefined, drawing: SHAPE_DRAWING,
})

/** A grouping holding two elements, and one element outside it. */
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test',
  name: 'Test',
  canvas: at(0, 0, 600, 400),
  backdrop: [],
  surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] },
  elements: [
    element('A', 'APP@1.a', at(20, 40, 120, 80), 'G'),
    element('B', 'APP@2.b', at(140, 40, 240, 80), 'G'),
    element('C', 'APP@3.c', at(400, 40, 500, 80)),
  ],
  boxes: [{
    alias: 'G', kind: 'authored-grouping', section: 'boxes', key: 'g-1', label: 'Group',
    extent: at(10, 10, 250, 90), inside: undefined, words: [], title_band: at(86, 10, 164, 28),
    drawing: SHAPE_DRAWING,
  }],
  relations: [{
    index: 0, key: 'r', source: 'B', target: 'C', decorated: [false, true],
    course: [[240, 60], [400, 60]], label: '', label_size: undefined, drawing: LINE_DRAWING,
  }],
}

const drawn = drawnArrangement(geometry)

describe('a layout written down and read back', () => {
  it('places every shape where the arrangement had it', () => {
    const arranged = resized(geometry, moved(geometry, drawn, 'C', 30, 20), 'A', at(20, 40, 160, 90))
    const back = arrangedBy(geometry, layoutOf(geometry, arranged))
    expect(placementOf(geometry, back)).toEqual(placementOf(geometry, arranged))
  })

  it('states a size only for an element that was resized', () => {
    const written = layoutOf(geometry, resized(geometry, drawn, 'A', at(20, 40, 160, 90)))
    expect(written.elements['APP@1.a']).toEqual({ x: 20, y: 40, w: 140, h: 50 })
    expect(written.elements['APP@3.c']).toEqual({ x: 400, y: 40 })
    expect(written.boxes['g-1']).toMatchObject({ x: 10, y: 10 })
  })
})

describe('the patch between two layouts', () => {
  it('changes only what differs, each entry read as what was stored', () => {
    const stored = layoutOf(geometry, drawn)
    const wanted = layoutOf(geometry, moved(geometry, drawn, 'C', 30, 20))
    const patch = layoutPatchBetween(stored, wanted)
    expect(patch.elements).toEqual({
      'APP@3.c': { value: { x: 430, y: 60 }, based_on: { x: 400, y: 40 } },
    })
    expect(patch.boxes).toEqual({})
  })

  it('removes every stored entry when the diagram returns to automatic', () => {
    const stored = layoutOf(geometry, drawn)
    const patch = layoutPatchBetween(stored, null)
    expect(Object.values(patch.elements).every((change) => change.value === null)).toBe(true)
    expect(Object.keys(patch.elements)).toHaveLength(3)
    expect(patchIsEmpty(layoutPatchBetween(stored, stored))).toBe(true)
  })
})

describe('what an edit arranged', () => {
  it('counts a moved element once', () => {
    expect(arrangedUnits(geometry, drawn, moved(geometry, drawn, 'C', 30, 20))).toEqual(['C'])
  })

  it('counts a box moved with its contents as one change', () => {
    expect(arrangedUnits(geometry, drawn, moved(geometry, drawn, 'G', 0, 50))).toEqual(['G'])
  })

  it('does not count a box that only grew round a moved member', () => {
    expect(arrangedUnits(geometry, drawn, moved(geometry, drawn, 'A', -5, 30))).toEqual(['A'])
  })

  it('counts nothing once a move is undone', () => {
    const there = moved(geometry, drawn, 'C', 30, 20)
    expect(arrangedUnits(geometry, drawn, moved(geometry, there, 'C', -30, -20))).toEqual([])
  })
})

describe('a line\'s stated route', () => {
  const bent = { ...drawn, routes: new Map([['r', {
    from: { side: 'right' as const, at: 0.5 }, to: { side: 'left' as const, at: 0.5 }, via: [[300, 60], [300, 150], [360, 150], [360, 60]] as const,
  }]]) }

  it('is written under relations by its key, read back, and patched like any other entry', () => {
    const written = layoutOf(geometry, bent)
    expect(written.relations).toEqual({ r: bent.routes.get('r') })
    expect(arrangedBy(geometry, written).routes.get('r')).toEqual(bent.routes.get('r'))
    const patch = layoutPatchBetween(layoutOf(geometry, drawn), written)
    expect(patch.relations).toEqual({ r: { value: bent.routes.get('r'), based_on: null } })
    expect(patchIsEmpty(layoutPatchBetween(written, written))).toBe(true)
    expect(shapedLines(geometry, drawn, bent)).toEqual([0])
  })

  it('moves bends and all when both its ends move together, and stays attached when one does', () => {
    const geometryBoth = { ...geometry, relations: [{ ...geometry.relations[0], source: 'A', target: 'B' }] }
    const together = moved(geometryBoth, bent, 'G', 10, 5)
    expect(together.routes.get('r')?.via?.[0]).toEqual([310, 65])
    const one = moved(geometry, bent, 'C', 0, 30)
    expect(one.routes.get('r')?.via?.at(-1)).toEqual([360, 90])
  })
})

describe('what Save states for the lines the session moved', () => {
  const routed = new Map<string, RoutedConnector>([['0', {
    key: '0', sourcePort: { side: 'right', at: 0.5 }, targetPort: { side: 'left', at: 0.5 },
    course: [{ x: 240, y: 60 }, { x: 320, y: 60 }, { x: 320, y: 120 }, { x: 400, y: 120 }],
  }]])
  const before = drawnArrangement(geometry)

  it('states the shown course of a line whose end moved', () => {
    const now = moved(geometry, before, 'C', 0, 60)
    expect(shownRoutesOfMoved(geometry, before, now, routed)).toEqual({
      r: { from: { side: 'right', at: 0.5 }, to: { side: 'left', at: 0.5 }, via: [[320, 60], [320, 120]] },
    })
  })

  it('leaves a line nothing moved to the router', () => {
    expect(shownRoutesOfMoved(geometry, before, before, routed)).toEqual({})
  })

  it('states the shown course of a line routed again because something moved across it', () => {
    expect(shownRoutesOfMoved(geometry, before, before, routed, new Set([0]))).toEqual({
      r: { from: { side: 'right', at: 0.5 }, to: { side: 'left', at: 0.5 }, via: [[320, 60], [320, 120]] },
    })
  })

  it('keeps a route the user stated', () => {
    const stated = new Map([['r', { via: [[300, 70]] as [number, number][] }]])
    const now = { ...moved(geometry, before, 'C', 0, 60), routes: stated }
    expect(shownRoutesOfMoved(geometry, before, now, routed)).toEqual({})
  })
})

