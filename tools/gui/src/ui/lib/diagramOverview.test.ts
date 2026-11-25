// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import {
  drawingCopyOf, drawnMarksOf, extentOfMarks, markExtent, overviewShapeOf, pictureBoxOf, pictureTextSizeOf,
  windowShowsAll,
} from './diagramOverview'

const extent = (left: number, top: number, right: number, bottom: number) => ({ left, top, right, bottom })

describe('the overview takes the picture\'s shape', () => {
  it('is a strip along the bottom for a picture wider than 4 : 1, keeping its aspect', () => {
    const shape = overviewShapeOf(extent(0, 0, 23211, 2592), 1200)
    expect(shape.kind).toBe('strip')
    expect(shape.width).toBeLessThanOrEqual(900)
    expect(shape.height).toBeLessThanOrEqual(96)
    expect(shape.width / shape.height).toBeCloseTo(23211 / 2592, 0)
  })

  it('never grows a strip past the canvas it sits in', () => {
    expect(overviewShapeOf(extent(0, 0, 9000, 1000), 500).width).toBeLessThanOrEqual(476)
  })

  it('is a corner map for any other picture, no larger than 220 × 140', () => {
    const wide = overviewShapeOf(extent(0, 0, 3000, 1000), 1200)
    const tall = overviewShapeOf(extent(0, 0, 800, 2400), 1200)
    for (const shape of [wide, tall]) {
      expect(shape.kind).toBe('corner')
      expect(shape.width).toBeLessThanOrEqual(220)
      expect(shape.height).toBeLessThanOrEqual(140)
    }
    expect(wide.width / wide.height).toBeCloseTo(3, 0)
  })

  it('leaves the zoom cluster in the bottom left corner clear of a strip centred along the bottom', () => {
    // The cluster spans the first 126 px from the canvas's left edge.
    for (const canvas of [790, 1100, 1500]) {
      const shape = overviewShapeOf(extent(0, 0, 34237, 1944), canvas)
      expect((canvas - shape.width) / 2).toBeGreaterThan(126)
    }
  })
})

describe('every element a viewer found, as a mark', () => {
  it('marks each where its drawings are, named, the selected ones selected', () => {
    const drawing = (x: number, y: number) => {
      const element = document.createElementNS('http://www.w3.org/2000/svg', 'g')
      Object.assign(element, { getBBox: () => ({ x, y, width: 50, height: 20 }) })
      return element
    }
    const marks = drawnMarksOf(
      new Map([['a', [drawing(0, 0), drawing(100, 0)]], ['b', [drawing(10, 50)]], ['undrawn', []]]),
      (id) => (id === 'a' ? 'Alpha' : undefined), new Set(['b']),
    )
    expect(marks).toEqual([
      { id: 'a', name: 'Alpha', selected: false, extent: { left: 0, top: 0, right: 150, bottom: 20 } },
      { id: 'b', name: 'b', selected: true, extent: { left: 10, top: 50, right: 60, bottom: 70 } },
    ])
  })
})

describe('the overview hides while it has nothing to tell', () => {
  it('reads a window over the whole picture as showing all, and one inside it as not', () => {
    const picture = extent(0, 0, 1000, 500)
    expect(windowShowsAll(extent(-20, -10, 1020, 510), picture)).toBe(true)
    expect(windowShowsAll(extent(100, 0, 1000, 500), picture)).toBe(false)
  })
})

describe('what F frames', () => {
  it('is the part of the picture every mark covers, and nothing without marks', () => {
    const marks = [
      { id: 'a', extent: extent(0, 0, 10, 10), selected: true },
      { id: 'b', extent: extent(500, 40, 520, 60), selected: false },
    ]
    expect(extentOfMarks(marks)).toEqual(extent(0, 0, 520, 60))
    expect(extentOfMarks([])).toBeNull()
  })
})

describe('a mark survives the overview\'s scale', () => {
  it('is never smaller than the least size, and stays centred on the element', () => {
    const mark = markExtent(extent(100, 100, 102, 104), 50)
    expect(mark.right - mark.left).toBe(50)
    expect(mark.bottom - mark.top).toBe(50)
    expect((mark.left + mark.right) / 2).toBe(101)
  })
})

const svgOf = (markup: string): SVGSVGElement => {
  const holder = document.createElement('div')
  holder.innerHTML = markup
  return holder.querySelector('svg')!
}

describe('the overview shows a still copy of the picture, and nothing more', () => {
  it('copies what a canvas marks as its drawing, leaving its marks and handles out', () => {
    const svg = svgOf(`<svg viewBox="0 0 10 10"><g data-picture-drawing><rect class="a"/></g>
      <g class="handles"><rect/></g></svg>`)
    const copy = drawingCopyOf(svg)
    expect(copy).toHaveLength(1)
    expect(copy[0].querySelector('rect.a')).not.toBeNull()
  })

  it('copies every drawn child of a picture that marks none, without its defs', () => {
    const svg = svgOf('<svg viewBox="0 0 10 10"><defs><marker id="m"/></defs><g><text>x</text></g></svg>')
    expect(drawingCopyOf(svg).map((part) => part.tagName.toLowerCase())).toEqual(['g'])
  })

  it('strips what would make the copy findable, focusable or announced, and keeps a component\'s scope', () => {
    const svg = svgOf(`<svg viewBox="0 0 10 10"><g id="root" data-entity-id="E1" tabindex="-1" role="button"
      aria-label="E1" data-v-abc="" class="kept"><rect id="r" data-conn-id="C1"/></g></svg>`)
    const [copy] = drawingCopyOf(svg)
    const gone = ['id', 'data-entity-id', 'tabindex', 'role', 'aria-label']
    for (const name of gone) expect(copy.hasAttribute(name)).toBe(false)
    expect(copy.hasAttribute('data-v-abc')).toBe(true)
    expect(copy.getAttribute('class')).toBe('kept')
    expect(copy.querySelector('[id], [data-conn-id]')).toBeNull()
    // The picture itself is untouched.
    expect(svg.querySelector('#root')?.getAttribute('data-entity-id')).toBe('E1')
  })

  it('reads the picture\'s box from its viewBox', () => {
    expect(pictureBoxOf(svgOf('<svg viewBox="5 6 100 50"></svg>'))).toEqual(extent(5, 6, 105, 56))
  })
})

describe('the picture\'s text size', () => {
  it('is the middle of its texts\' sizes, so a title does not decide it', () => {
    const svg = svgOf(`<svg><text font-size="12">a</text><text font-size="12">b</text>
      <text font-size="22">title</text></svg>`)
    expect(pictureTextSizeOf(svg)).toBe(12)
  })

  it('is unknown for a picture with no sized text', () => {
    expect(pictureTextSizeOf(svgOf('<svg><text>a</text></svg>'))).toBeNull()
  })
})
