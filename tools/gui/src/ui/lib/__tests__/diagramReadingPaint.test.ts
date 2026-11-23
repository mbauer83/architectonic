// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { clearReading, paintReading } from '../diagramReadingPaint'

const SVG = `<svg xmlns="http://www.w3.org/2000/svg">
  <g id="a"><rect width="10" height="10"/><text>A</text></g>
  <g id="b"><rect x="50" width="10" height="10"/></g>
  <g id="c"><rect x="90" width="10" height="10"/></g>
  <g id="ab"><path d="M10 5 L50 5"/><polygon points="0,0 1,1"/></g>
  <g id="bc"><path d="M60 5 L90 5"/></g>
</svg>`

const picture = () => {
  const host = document.createElement('div')
  host.innerHTML = SVG
  const svg = host.querySelector('svg') as SVGSVGElement
  const at = (id: string) => [svg.querySelector(`#${id}`) as Element]
  const nodes = new Map([['A', at('a')], ['B', at('b')], ['C', at('c')]])
  const edges = new Map([['AB', at('ab')], ['BC', at('bc')]])
  return { svg, nodes, edges, at }
}

describe('marking a reading on the picture', () => {
  it('dims what the reading does not reach and keeps the relations it crossed', () => {
    const { svg, nodes, edges, at } = picture()
    paintReading(svg, nodes, edges, { lit: new Set(['A', 'B']), relations: new Set(['AB']), flow: null })

    expect(svg.classList.contains('reading-on')).toBe(true)
    expect(at('c')[0].classList.contains('reading-dim')).toBe(true)
    expect(at('a')[0].classList.contains('reading-dim')).toBe(false)
    expect(at('ab')[0].classList.contains('reading-lit')).toBe(true)
    expect(at('bc')[0].classList.contains('reading-dim')).toBe(true)
    expect(svg.querySelectorAll('[data-reading-flow]')).toHaveLength(0)
  })

  it('lays flow over each line of a crossed relation: travelling when directed, a pulse when not', () => {
    const { svg, nodes, edges } = picture()
    const flow = new Map([['AB', { directed: true, target: nodes.get('B') ?? [] }], ['BC', { directed: false, target: [] }]])
    paintReading(svg, nodes, edges, { lit: new Set(['A', 'B', 'C']), relations: new Set(['AB', 'BC']), flow })

    const laid = [...svg.querySelectorAll('[data-reading-flow]')]
    expect(laid.map((one) => one.getAttribute('class'))).toEqual(['reading-flow', 'reading-flow reading-flow--pulse'])
    // The copy carries the line's geometry and nothing that styles the line itself.
    expect(laid[0].getAttribute('d')).toBe('M10 5 L50 5')
    expect(laid[0].tagName.toLowerCase()).toBe('path')
  })

  it('replaces an earlier reading, and clearing leaves the picture as it was drawn', () => {
    const { svg, nodes, edges } = picture()
    const before = svg.outerHTML
    const flow = new Map([['AB', { directed: true, target: [] }]])
    paintReading(svg, nodes, edges, { lit: new Set(['A']), relations: new Set(['AB']), flow })
    paintReading(svg, nodes, edges, { lit: new Set(['C']), relations: new Set(), flow: null })
    expect(svg.querySelectorAll('[data-reading-flow]')).toHaveLength(0)
    expect(svg.querySelectorAll('.reading-dim')).toHaveLength(4)

    clearReading(svg)
    expect(svg.outerHTML.replace(/ class=""/g, '')).toBe(before)
  })
})
