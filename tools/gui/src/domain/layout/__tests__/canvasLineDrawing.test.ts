/**
 * The canvas draws a line as the composer does: held to `tests/fixtures/layout_geometry/line_drawing.json`,
 * which pytest holds to `relation_drawing` and `relation_decorations`. And it draws it with PlantUML's
 * own stroke and decorations, never a look of its own.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import type { Point } from '../geometry'
import type { DrawingNode, LineDrawing } from '../../schemas/diagramLayoutGeometry'
import { decorationMotion, drawnLine, headingAtEnd, roundedPath, stoppingShort, transformOf } from '../canvasLineDrawing'

type XY = readonly [number, number]

interface Case {
  readonly name: string
  readonly course: readonly XY[]
  readonly path: string
  readonly heading: XY
  readonly short: readonly { readonly gaps: XY; readonly course: readonly XY[] }[]
  readonly decorations: readonly { readonly at: XY; readonly heading: XY; readonly to: XY; readonly degrees: number }[]
}

const FIXTURE = new URL('../../../../../../tests/fixtures/layout_geometry/line_drawing.json', import.meta.url)
const { cases } = JSON.parse(readFileSync(fileURLToPath(FIXTURE), 'utf-8')) as { cases: readonly Case[] }

const points = (course: readonly XY[]): Point[] => course.map(([x, y]) => ({ x, y }))

describe.each(cases)('a line drawn along $name', (one) => {
  const course = points(one.course)

  it('rounds its bends as the composer does', () => {
    expect(roundedPath(course)).toBe(one.path)
  })

  it('arrives heading the way the composer reads it', () => {
    const heading = headingAtEnd(course)
    expect([heading.x, heading.y]).toEqual(one.heading)
  })

  it('stops short of its decorations by their gaps', () => {
    for (const { gaps, course: short } of one.short) {
      const drawn = stoppingShort(course, gaps[0], gaps[1])
      drawn.forEach((point, index) => {
        expect(point.x).toBeCloseTo(short[index][0], 9)
        expect(point.y).toBeCloseTo(short[index][1], 9)
      })
    }
  })

  it('turns its decorations to face its end', () => {
    for (const decoration of one.decorations) {
      const motion = decorationMotion(decoration, course)
      expect([motion.to.x, motion.to.y]).toEqual(decoration.to)
      expect(motion.degrees).toBeCloseTo(decoration.degrees, 9)
    }
  })
})

const node = (tag: string, attributes: Record<string, string> = {}): DrawingNode =>
  ({ tag, attributes, text: undefined, children: [] })

describe('a line drawn with PlantUML\'s drawing', () => {
  const stroke = node('path', { d: 'M0,0 L1,1', fill: 'none', style: 'stroke:#181818;stroke-width:1;stroke-dasharray:7,7;' })
  const head = node('polygon', { points: '0,0 4,10 8,0', fill: '#181818' })
  const drawing: LineDrawing = {
    group: node('g'),
    line: stroke,
    ends: [
      { marks: [], at: [0, 0], heading: [-1, 0], gap: 0 },
      { marks: [head], at: [4, 10], heading: [0, 1], gap: 10 },
    ],
    label: { texts: [node('text', { x: '0', y: '0' })], centre: [5, 5] },
  }
  const course = [{ x: 0, y: 0 }, { x: 100, y: 0 }]

  it('keeps PlantUML\'s stroke and runs it along the course, short of the hollow head', () => {
    const drawn = drawnLine(drawing, course)
    expect(drawn.line.attributes.style).toBe(stroke.attributes.style)
    expect(drawn.line.attributes.d).toBe('M0,0 L90,0')
  })

  it('carries PlantUML\'s decoration to the end, turned to face along the course', () => {
    const drawn = drawnLine(drawing, course)
    expect(drawn.ends[1].marks).toEqual([head])
    expect(drawn.ends[1].transform).toBe(transformOf({ pivot: { x: 4, y: 10 }, to: { x: 100, y: 0 }, degrees: -90 }))
  })

  it('carries the label to the middle of the course', () => {
    expect(drawnLine(drawing, course).label?.transform).toBe('translate(45 -5)')
  })
})
