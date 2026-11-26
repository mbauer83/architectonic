/**
 * A shape on the canvas is drawn with PlantUML's own drawing: shifted where it was only moved, and as the
 * composer drew it at its new size where it was resized — the same drawing for every occurrence of
 * one element at one size, whichever was moved.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../geometry'
import { shapeDrawing, stillToReshape } from '../canvasShapeDrawing'
import { drawingNode } from './canvasDrawingFixtures'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

const plantuml = drawingNode('path', { fill: '#B5FFFF', style: 'stroke:#181818;stroke-width:0.5;' })
const composed = drawingNode('path', { fill: '#B5FFFF', d: 'M0,0 L200,0' })

describe('a shape drawn on the canvas', () => {
  const drawn = at(100, 100, 220, 150)

  it('is PlantUML\'s own drawing, shifted, where it was only moved', () => {
    expect(shapeDrawing(drawn, plantuml, at(130, 90, 250, 140), undefined)).toEqual({
      drawing: plantuml, transform: 'translate(30 -10)',
    })
  })

  it('is the composer\'s drawing at its new size, shifted from where that was drawn', () => {
    const reshaped = { at: at(100, 100, 300, 150), drawing: composed }
    expect(shapeDrawing(drawn, plantuml, at(150, 200, 350, 250), reshaped)).toEqual({
      drawing: composed, transform: 'translate(50 100)',
    })
  })

  it('goes back to PlantUML\'s drawing once it is its drawn size again', () => {
    const reshaped = { at: at(100, 100, 300, 150), drawing: composed }
    expect(shapeDrawing(drawn, plantuml, drawn, reshaped).drawing).toBe(plantuml)
  })

  it('draws two occurrences of one element alike: each is its own PlantUML drawing, shifted', () => {
    const first = shapeDrawing(drawn, plantuml, at(400, 100, 520, 150), undefined)
    const second = shapeDrawing(at(0, 300, 120, 350), plantuml, at(400, 300, 520, 350), undefined)
    expect(first.drawing).toBe(second.drawing)
  })
})

describe('the shapes still to be drawn at their new size', () => {
  const drawnAt = new Map([['A', at(0, 0, 100, 50)], ['B', at(0, 100, 100, 150)], ['C', at(0, 200, 100, 250)]])

  it('are the resized ones the composer has not yet drawn at that size', () => {
    const now = new Map([
      ['A', at(10, 0, 110, 50)],
      ['B', at(0, 100, 160, 150)],
      ['C', at(0, 200, 140, 250)],
    ])
    const reshaped = new Map([['C', { at: at(50, 50, 190, 100), drawing: composed }]])
    expect(stillToReshape(drawnAt, now, reshaped)).toEqual(['B'])
  })
})
