// @vitest-environment jsdom
//
// The lab draws PlantUML's drawing as it was handed over — every attribute that sets the look kept —
// and nothing that is not drawing: no other element, no handler, no link that fetches.

import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, type App } from 'vue'
import type { DrawingNode } from '../../../domain/schemas/diagramLayoutGeometry'
import LabDrawn, { drawnAttributes } from './LabDrawn'

const node = (tag: string, attributes: Record<string, string>, text: string | undefined = undefined, children: DrawingNode[] = []) =>
  ({ tag, attributes, text, children })

let app: App | null = null

const drawn = (nodes: DrawingNode[], transform?: string): SVGSVGElement => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h('svg', [h(LabDrawn, { nodes, transform })]) })
  app.mount(host)
  return host.querySelector('svg') as SVGSVGElement
}

afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
})

describe('a drawing in the lab', () => {
  it('keeps PlantUML\'s fill, stroke and font, in SVG', () => {
    const outline = node('path', { d: 'M0,0 L10,0', fill: '#D1BADC', style: 'stroke:#3F3842;stroke-width:0.5;' })
    const word = node('text', { 'font-family': 'sans-serif', 'font-size': '12', textLength: '58.6641', x: '1', y: '2' }, 'Increased')
    const svg = drawn([node('g', { class: 'entity' }, undefined, [outline, word])], 'translate(3 4)')

    expect(svg.querySelector('g')?.getAttribute('transform')).toBe('translate(3 4)')
    const path = svg.querySelector('path')
    expect(path?.namespaceURI).toBe('http://www.w3.org/2000/svg')
    expect(path?.getAttribute('fill')).toBe('#D1BADC')
    expect(path?.getAttribute('style')?.replace(/\s/g, '')).toContain('stroke:rgb(63,56,66)')
    const text = svg.querySelector('text')
    expect(text?.getAttribute('font-size')).toBe('12')
    expect(text?.getAttribute('textLength')).toBe('58.6641')
    expect(text?.textContent).toBe('Increased')
  })

  it('leaves out what is not drawing', () => {
    const svg = drawn([node('script', {}, 'alert(1)'), node('rect', { x: '0', onclick: 'alert(1)' })])

    expect(svg.querySelector('script')).toBeNull()
    expect(svg.querySelector('rect')?.getAttribute('onclick')).toBeNull()
  })

  it('lets an image carry its own picture and fetch nothing', () => {
    expect(drawnAttributes(node('image', { href: 'data:image/png;base64,AAAA', x: '0' }))).toEqual({
      href: 'data:image/png;base64,AAAA', x: '0',
    })
    expect(drawnAttributes(node('image', { 'xlink:href': 'https://example.org/x.png' }))).toEqual({})
  })
})
