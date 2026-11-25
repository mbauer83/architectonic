/**
 * The title and the legend ride with the diagram as it is arranged, by the composer's rule: a part keeps
 * to the side or the middle it was drawn at, below or above. A picture not moved moves nothing.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../../geometry'
import { carriedBy, carriedSurround, occupiedBy } from '../labSurround'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const NODE = { tag: 'g', attributes: {}, children: [] }

describe('a part drawn round the diagram', () => {
  const was = at(100, 100, 500, 400)
  const now = at(100, 100, 700, 600)

  it('keeps a title centred above the diagram', () => {
    expect(carriedBy(at(250, 40, 350, 60), was, now)).toEqual({ x: 100, y: 0 })
  })

  it('keeps a legend below it, at the side it was drawn at', () => {
    expect(carriedBy(at(520, 420, 600, 480), was, now)).toEqual({ x: 200, y: 200 })
    expect(carriedBy(at(20, 420, 90, 480), was, now)).toEqual({ x: 0, y: 200 })
  })

  it('stays put while the diagram has not moved', () => {
    const occupied = occupiedBy([at(100, 100, 300, 200)], [[{ x: 300, y: 150 }, { x: 500, y: 400 }]])
    expect(occupied).toEqual(was)
    expect(carriedSurround([{ drawing: NODE, extent: at(250, 40, 350, 60) }], occupied, occupied)[0].by)
      .toEqual({ x: 0, y: 0 })
  })

  it('carries its extent with it, which the view takes in', () => {
    const [legend] = carriedSurround([{ drawing: NODE, extent: at(520, 420, 600, 480) }], was, now)
    expect(legend.extent).toEqual(at(720, 620, 800, 680))
  })
})
