/**
 * The canvas's arrangement keeps the composer's box rule: a box holds its members because it grows to
 * hold them, moving a box carries what it holds, a stated size widens and never narrows, and the
 * layout block states only what differs from PlantUML's picture.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../../geometry'
import {
  descendantsOf,
  drawnArrangement,
  fittedBoxes,
  moved,
  resized,
  resizedExtent,
} from '../labArrangement'
import { LINE_DRAWING, SHAPE_DRAWING } from './labDrawingFixtures'
import type { LayoutGeometry } from '../../../schemas/diagramLayoutGeometry'
import { changedShapes, placementOf, textRegions, widenedArrangement } from '../labRouting'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

/** A grouping holding two elements, one element outside it, and a relation between the outer two. */
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test',
  name: 'Test',
  canvas: at(0, 0, 600, 400),
  backdrop: [],
  elements: [
    { alias: 'A', key: 'APP@1.a', label: 'A', extent: at(20, 40, 120, 80), inside: 'G', words: [], outside_label: undefined, drawing: SHAPE_DRAWING },
    { alias: 'B', key: 'APP@2.b', label: 'B', extent: at(140, 40, 240, 80), inside: 'G', words: [], outside_label: undefined, drawing: SHAPE_DRAWING },
    { alias: 'C', key: 'APP@3.c', label: 'C', extent: at(400, 40, 500, 80), inside: undefined, words: [], outside_label: undefined, drawing: SHAPE_DRAWING },
  ],
  boxes: [
    {
      alias: 'G', kind: 'authored-grouping', section: 'boxes', key: 'g-1', label: 'Group',
      extent: at(10, 10, 250, 90), inside: undefined,
      words: [{ text: 'Group', x: 110, y: 25, width: 30 }],
      title_band: at(86, 10, 164, 28), drawing: SHAPE_DRAWING,
    },
  ],
  relations: [
    {
      index: 0, key: 'r', source: 'B', target: 'C', decorated: [false, true],
      course: [[240, 60], [400, 60]], label: '', label_size: undefined, drawing: LINE_DRAWING,
    },
  ],
}

describe('the canvas arrangement', () => {
  it('fits a box round its members with the padding PlantUML gave it', () => {
    const boxes = fittedBoxes(geometry, drawnArrangement(geometry))
    expect(boxes.get('G')).toEqual(at(10, 10, 250, 90))
  })

  it('grows a box to hold a member dragged out of it', () => {
    const arrangement = moved(geometry, drawnArrangement(geometry), 'B', 100, 50)
    const box = fittedBoxes(geometry, arrangement).get('G')
    expect(box).toEqual(at(10, 10, 350, 140))
  })

  it('carries a box members with it', () => {
    const arrangement = moved(geometry, drawnArrangement(geometry), 'G', 30, 20)
    expect(arrangement.elements.get('A')).toEqual(at(50, 60, 150, 100))
    expect(arrangement.elements.get('C')).toEqual(at(400, 40, 500, 80))
    expect(fittedBoxes(geometry, arrangement).get('G')).toEqual(at(40, 30, 280, 110))
  })

  it('widens a box to a stated size and never narrows it below its members', () => {
    const grown = resized(geometry, drawnArrangement(geometry), 'G', at(10, 10, 400, 200))
    expect(fittedBoxes(geometry, grown).get('G')).toEqual(at(10, 10, 400, 200))
    const shrunk = resized(geometry, drawnArrangement(geometry), 'G', at(10, 10, 100, 50))
    expect(fittedBoxes(geometry, shrunk).get('G')).toEqual(at(10, 10, 250, 90))
  })

  it('names every shape a box holds', () => {
    expect(descendantsOf(geometry, 'G')).toEqual(['A', 'B'])
  })

  it('keeps a resize at least as large as it is told, from whichever side is dragged', () => {
    expect(resizedExtent(at(0, 0, 100, 50), 'se', 20, 10, 24)).toEqual(at(0, 0, 120, 60))
    expect(resizedExtent(at(0, 0, 100, 50), 'nw', 200, 200, 24)).toEqual(at(76, 26, 100, 50))
  })

})

describe('the canvas picture as the router sees it', () => {
  it('names the shapes a change moved, boxes that grew among them', () => {
    const before = placementOf(geometry, drawnArrangement(geometry))
    const after = placementOf(geometry, moved(geometry, drawnArrangement(geometry), 'B', 100, 0))
    expect([...changedShapes(before, after)].sort()).toEqual(['B', 'G'])
  })

  it('keeps lines out of a box title band only as wide as the title, carried with the box', () => {
    const placement = placementOf(geometry, moved(geometry, drawnArrangement(geometry), 'G', 0, 30))
    // The title's words run 110..140; the band reaches BAND_MARGIN either side: a routing obstacle only.
    expect(textRegions(geometry, placement).get('band:G')).toEqual(at(86, 40, 164, 58))
  })

  it('widens as a first layout does, keeping every element and every member inside its box', () => {
    const opened = widenedArrangement(geometry, drawnArrangement(geometry))
    expect([...opened.elements.keys()].sort()).toEqual(['A', 'B', 'C'])
    const box = fittedBoxes(geometry, opened).get('G') as Extent
    for (const alias of ['A', 'B']) {
      const member = opened.elements.get(alias) as Extent
      expect(member.left >= box.left && member.right <= box.right).toBe(true)
    }
  })
})
