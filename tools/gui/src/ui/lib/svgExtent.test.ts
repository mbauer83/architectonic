// @vitest-environment jsdom
//
// Where a large picture opens (Q19): on the box nearest its top-left corner, not on the corner itself,
// where lines running above every box may leave nothing to read.
import { describe, expect, it } from 'vitest'
import { topLeftBoxOf } from './svgExtent'

const NS = 'http://www.w3.org/2000/svg'
const picture = (boxes: readonly (readonly [number, number, number, number])[]) => {
  const svg = document.createElementNS(NS, 'svg')
  for (const [x, y, width, height] of boxes) {
    const rect = document.createElementNS(NS, 'rect')
    Object.assign(rect, { getBBox: () => ({ x, y, width, height }) })
    svg.appendChild(rect)
  }
  return svg
}
const DRAWING = { left: 0, top: 0, right: 30000, bottom: 2000 }

describe('the top-left box of a picture', () => {
  it('is the drawn box nearest the picture\'s top-left corner', () => {
    const svg = picture([[0, 0, 30000, 2000], [40, 700, 3000, 900], [600, 650, 200, 60], [2, 2, 4, 4]])
    expect(topLeftBoxOf(svg, DRAWING)).toEqual({ x: 40, y: 700 })
  })

  it('is none where the picture draws only its paper and specks', () => {
    expect(topLeftBoxOf(picture([[0, 0, 30000, 2000], [10, 10, 3, 3]]), DRAWING)).toBeNull()
  })
})
