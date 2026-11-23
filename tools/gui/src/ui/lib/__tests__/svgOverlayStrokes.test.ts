// @vitest-environment jsdom
//
// The connection hit area and the reader's flow are both copies of a line's strokes laid over it. These
// hold the copy to the rules both depend on: geometry only, never a marker (the GSN giant-arrowhead
// defect: a marker with `markerUnits="strokeWidth"` scales with a widened stroke), never a stroke inside
// a drawn element, and never a copy of another copy.
import { describe, expect, it } from 'vitest'
import { addConnectionHitAreas, overlayStrokes } from '../svgHitAreas'

const edge = () => {
  const host = document.createElement('div')
  host.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg"><g id="edge">
    <path id="p" class="line" style="stroke:#20242A" d="M0 0 L10 0" stroke="#20242A" stroke-width="1.5"
      marker-end="url(#m)"/>
    <g data-entity-id="E"><path d="M5 5 L6 6"/></g>
  </g></svg>`
  return host.querySelector('#edge') as SVGGElement
}

describe('laying copies of a line over it', () => {
  it('gives a hit area the geometry and a wide transparent stroke, and nothing that styles the line', () => {
    const group = edge()
    addConnectionHitAreas(group)
    const hits = group.querySelectorAll('[data-conn-hit]')
    expect(hits).toHaveLength(1)
    const hit = hits[0]
    expect(hit.getAttribute('d')).toBe('M0 0 L10 0')
    expect(hit.getAttribute('marker-end')).toBeNull()
    expect(hit.getAttribute('id')).toBeNull()
    expect(hit.getAttribute('class')).toBeNull()
    expect(hit.getAttribute('stroke')).toBe('transparent')
    expect(hit.getAttribute('stroke-width')).toBe('12')
  })

  it('replaces its own earlier copies and never copies another overlay', () => {
    const group = edge()
    addConnectionHitAreas(group)
    overlayStrokes(group, 'data-flow', (copy) => copy.setAttribute('class', 'flow'))
    addConnectionHitAreas(group)
    overlayStrokes(group, 'data-flow', (copy) => copy.setAttribute('class', 'flow'))
    expect(group.querySelectorAll('[data-conn-hit]')).toHaveLength(1)
    expect(group.querySelectorAll('[data-flow]')).toHaveLength(1)
    expect(group.querySelectorAll('path')).toHaveLength(4)
  })
})
