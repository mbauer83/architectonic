/**
 * The keyboard's reach over a picture (sketch 02·9, 05·5): reading order by rows, the nearest shape in
 * an arrow's direction, and the Tab walk of edit mode with each box just before its first member.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../geometry'
import { inReadingOrder, nearestTowards, walkOrder } from '../keyboardReach'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const stop = (id: string, box: Extent) => ({ id, box })

describe('reading order', () => {
  it('reads top to bottom, and shapes whose tops are within a row left to right', () => {
    const shapes = [at(300, 4, 340, 40), at(0, 100, 40, 140), at(10, 0, 50, 40)]
    expect(shapes.sort(inReadingOrder)).toEqual([at(10, 0, 50, 40), at(300, 4, 340, 40), at(0, 100, 40, 140)])
  })
})

describe('the nearest shape in a direction', () => {
  const from = at(100, 100, 140, 140)
  const stops = [stop('right', at(300, 100, 340, 140)), stop('far-down', at(100, 400, 140, 440)),
    stop('right-up', at(200, 0, 240, 40))]

  it('takes what is ahead, weighing sideways distance double', () => {
    expect(nearestTowards(from, stops, { x: 1, y: 0 })?.id).toBe('right')
    expect(nearestTowards(from, stops, { x: 0, y: 1 })?.id).toBe('far-down')
  })

  it('finds nothing where nothing is ahead', () => {
    expect(nearestTowards(from, stops, { x: -1, y: 0 })).toBeNull()
  })
})

describe('the Tab walk of edit mode', () => {
  const inside: Record<string, string> = { a: 'G', b: 'G', g2: 'G', c: 'g2' }
  const containerOf = (id: string) => inside[id]

  it('puts a box just before its first member, outer boxes before inner ones', () => {
    const elements = [stop('x', at(0, 0, 40, 40)), stop('b', at(200, 100, 240, 140)), stop('a', at(100, 100, 140, 140)),
      stop('c', at(100, 300, 140, 340))]
    const boxes = [stop('G', at(90, 90, 400, 400)), stop('g2', at(95, 290, 150, 350))]
    expect(walkOrder(elements, boxes, containerOf)).toEqual(['x', 'G', 'a', 'b', 'g2', 'c'])
  })

  it('reads a box that holds no element at its own place', () => {
    const elements = [stop('x', at(0, 0, 40, 40)), stop('y', at(0, 300, 40, 340))]
    expect(walkOrder(elements, [stop('E', at(0, 100, 100, 200))], () => undefined)).toEqual(['x', 'E', 'y'])
  })
})
