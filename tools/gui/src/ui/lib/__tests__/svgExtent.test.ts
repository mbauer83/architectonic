// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { pictureExtentOf } from '../svgExtent'

const shape = (box: () => { x: number; y: number; width: number; height: number }) => {
  const element = document.createElementNS('http://www.w3.org/2000/svg', 'rect') as SVGGraphicsElement
  Object.defineProperty(element, 'getBBox', { value: box })
  return element
}

describe('where a picture element is drawn', () => {
  it('reads the box the browser lays it out in, in the picture’s own units', () => {
    expect(pictureExtentOf(shape(() => ({ x: 10, y: 20, width: 30, height: 5 }))))
      .toEqual({ left: 10, top: 20, right: 40, bottom: 25 })
  })

  it('says nothing for an element that is not drawn, or that the browser cannot measure', () => {
    expect(pictureExtentOf(document.createElement('div'))).toBeNull()
    expect(pictureExtentOf(shape(() => { throw new Error('not rendered') }))).toBeNull()
  })
})
