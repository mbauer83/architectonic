/**
 * The canvas fits its boxes by the composer's box rule, held to the cases the Python composer is held to.
 *
 * `tests/fixtures/layout_geometry/boxes.json` states a picture's boxes and elements as drawn, where the
 * elements are now and what is stated for a box, with the composer's answer (`arrangement.fitted_boxes`)
 * for every box. A box-padding, title-margin or widening change on one side fails here or in pytest.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import type { Extent } from '../../geometry'
import { fittedBoxes } from '../labArrangement'
import { SHAPE_DRAWING } from './labDrawingFixtures'
import type { LayoutGeometry, MeasuredWord } from '../../../schemas/diagramLayoutGeometry'

interface DrawnShape {
  alias: string
  extent: Extent
  inside: string | null
}

interface Boxes {
  elements: DrawnShape[]
  boxes: (DrawnShape & { words: MeasuredWord[] })[]
  cases: { name: string; moved: Record<string, Extent>; stated: Record<string, Extent>; fitted: Record<string, Extent> }[]
}

const fixture = JSON.parse(
  readFileSync(
    fileURLToPath(new URL('../../../../../../../tests/fixtures/layout_geometry/boxes.json', import.meta.url)),
    'utf-8',
  ),
) as Boxes

const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.boxes',
  name: 'Boxes',
  canvas: { left: 0, top: 0, right: 800, bottom: 600 },
  backdrop: [],
  surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] },
  elements: fixture.elements.map((one) => ({
    alias: one.alias, label: one.alias, extent: one.extent, inside: one.inside ?? undefined, words: [],
    drawing: SHAPE_DRAWING,
  })),
  boxes: fixture.boxes.map((one) => ({
    alias: one.alias, kind: 'authored-grouping', section: 'boxes', label: one.alias, extent: one.extent,
    inside: one.inside ?? undefined, words: one.words, drawing: SHAPE_DRAWING,
  })),
  relations: [],
}

const drawnElements = new Map(fixture.elements.map((one) => [one.alias, one.extent] as const))

describe('a box fitted on the canvas is where the composer draws it', () => {
  it.each(fixture.cases)('$name', ({ moved, stated, fitted }) => {
    const arrangement = {
      elements: new Map([...drawnElements, ...Object.entries(moved)]),
      stated: new Map(Object.entries(stated)),
      routes: new Map(),
    }
    expect(Object.fromEntries(fittedBoxes(geometry, arrangement))).toEqual(fitted)
  })

  it('holds every case the fixture states, and each one names every box', () => {
    expect(fixture.cases.length).toBeGreaterThan(5)
    for (const one of fixture.cases) expect(Object.keys(one.fitted).sort()).toEqual(fixture.boxes.map((b) => b.alias).sort())
  })
})
