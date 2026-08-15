// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { snapshotFilename, snapshotSvgMarkup } from '../graphSnapshot'

const FRAME = { x: -40, y: -20, w: 800, h: 600 }

const canvas = (inner: string): SVGSVGElement => {
  const host = document.createElement('div')
  host.innerHTML =
    `<svg class="graph-svg" viewBox="0 0 100 100" style="visibility:visible">${inner}</svg>`
  return host.querySelector('svg') as unknown as SVGSVGElement
}

describe('the snapshot is what is on screen, able to stand alone', () => {
  it('takes the frame the reader is looking at, not the element\'s own viewBox', () => {
    const markup = snapshotSvgMarkup(canvas('<g class="graph-node"/>'), FRAME)

    expect(markup).toContain('viewBox="-40 -20 800 600"')
  })

  it('states an absolute size as well, so it has one outside a browser', () => {
    // A bare viewBox scales to whatever box it lands in, and gives a rasteriser no pixel count.
    const markup = snapshotSvgMarkup(canvas(''), FRAME)

    expect(markup).toContain('width="800"')
    expect(markup).toContain('height="600"')
  })

  it('declares the SVG namespace, which the DOM knows implicitly and a file does not', () => {
    expect(snapshotSvgMarkup(canvas(''), FRAME)).toContain('http://www.w3.org/2000/svg')
  })

  it('carries a font, which was inherited from the page and is inherited from nothing in a file', () => {
    expect(snapshotSvgMarkup(canvas(''), FRAME)).toMatch(/font-family="[^"]+"/)
  })

  it('paints a ground behind everything, over the frame rather than the content', () => {
    const markup = snapshotSvgMarkup(canvas('<g/>'), FRAME, { background: '#fafafa' })

    // Dark-on-transparent is a picture of nothing once the page is not behind it.
    expect(markup).toMatch(/<rect[^>]*x="-40"[^>]*y="-20"[^>]*fill="#fafafa"/)
  })

  it('keeps the drawing itself', () => {
    const markup = snapshotSvgMarkup(canvas('<g class="graph-node"><title>GOL: A goal</title></g>'), FRAME)

    expect(markup).toContain('GOL: A goal')
  })

  it('drops the selection highlight, which is the pointer\'s state and not the model\'s', () => {
    const markup = snapshotSvgMarkup(
      canvas('<g class="graph-edge edge-selected"><path d="M0 0 L1 1"/></g>'), FRAME,
    )

    expect(markup).not.toContain('edge-selected')
    expect(markup).toContain('graph-edge')
  })

  it('drops the inline style the canvas uses to hide itself before its first fit', () => {
    expect(snapshotSvgMarkup(canvas(''), FRAME)).not.toContain('visibility')
  })

  it('leaves the live canvas untouched', () => {
    const live = canvas('<g class="graph-node"/>')

    snapshotSvgMarkup(live, FRAME)

    expect(live.getAttribute('viewBox')).toBe('0 0 100 100')
    expect(live.querySelector('rect')).toBeNull()
  })
})

describe('the filename says what it is and when', () => {
  const at = new Date('2026-08-15T09:41:07.500Z')

  it('carries the label and a sortable stamp', () => {
    expect(snapshotFilename('Sustain Unity of Effort', 'svg', at))
      .toBe('Sustain-Unity-of-Effort_2026-08-15_09-41-07.svg')
  })

  it('keeps an artifact id readable rather than mangling it', () => {
    expect(snapshotFilename('GOL@1780220699.FCfDuc.sustain-unity', 'png', at))
      .toBe('GOL-1780220699.FCfDuc.sustain-unity_2026-08-15_09-41-07.png')
  })

  it('falls back to a name rather than producing a file called nothing', () => {
    expect(snapshotFilename('///', 'svg', at)).toBe('graph_2026-08-15_09-41-07.svg')
  })

  it('bounds the length, since a label may be a sentence', () => {
    const name = snapshotFilename('x'.repeat(200), 'svg', at)

    expect(name.length).toBeLessThan(110)
  })
})
