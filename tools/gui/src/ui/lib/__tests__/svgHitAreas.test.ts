/**
 * Regression coverage for the GSN giant-arrowhead defect: a connection hit-area clone must
 * never carry a `marker-*` attribute, since GSN's markers use `markerUnits="strokeWidth"` and
 * would scale up with the hit area's widened stroke-width.
 *
 * No jsdom/happy-dom in this project (see DiagramDetailView.drilldown.test.ts) — a minimal
 * fake standing in for the SVGElement attribute API is used instead of a real DOM element.
 */
import { describe, it, expect } from 'vitest'
import { SVG_MARKER_ATTRIBUTES, stripMarkerAttributes } from '../svgHitAreas'

class FakeSvgElement {
  private attrs = new Map<string, string>()

  set(name: string, value: string): this {
    this.attrs.set(name, value)
    return this
  }

  getAttribute(name: string): string | null {
    return this.attrs.get(name) ?? null
  }

  removeAttribute(name: string): void {
    this.attrs.delete(name)
  }

  get attributes(): { name: string; value: string }[] {
    return Array.from(this.attrs, ([name, value]) => ({ name, value }))
  }
}

// A fixture line as emitted by src/diagram_types/gsn/svg_renderer.py's _edge().
const gsnEdgeFixture = () =>
  new FakeSvgElement()
    .set('x1', '0')
    .set('y1', '0')
    .set('x2', '10')
    .set('y2', '10')
    .set('stroke', '#20242A')
    .set('stroke-width', '1.5')
    .set('marker-end', 'url(#gsn-filled-arrow)')

describe('SVG_MARKER_ATTRIBUTES', () => {
  it('names exactly the three marker-reference attributes', () => {
    expect(SVG_MARKER_ATTRIBUTES).toEqual(['marker-start', 'marker-mid', 'marker-end'])
  })
})

describe('stripMarkerAttributes', () => {
  it('removes marker-end from a shallow clone (AssuranceDiagramPanel pattern)', () => {
    const hit = gsnEdgeFixture()
    expect(hit.getAttribute('marker-end')).toBe('url(#gsn-filled-arrow)')

    stripMarkerAttributes(hit as unknown as SVGElement)

    expect(hit.getAttribute('marker-end')).toBeNull()
    expect(hit.getAttribute('stroke-width')).toBe('1.5')
  })

  it('is a no-op when no marker attribute is present', () => {
    const el = new FakeSvgElement().set('stroke-width', '12')
    stripMarkerAttributes(el as unknown as SVGElement)
    expect(el.getAttribute('stroke-width')).toBe('12')
  })
})

describe('attribute-copy hit-area pattern (DiagramDetailView)', () => {
  it('excludes marker-end when copying attributes onto a new hit-area element', () => {
    const source = gsnEdgeFixture()
    const hit = new FakeSvgElement()
    const skipped: readonly string[] = ['id', 'class', 'style', ...SVG_MARKER_ATTRIBUTES]
    for (const attr of source.attributes) {
      if (skipped.includes(attr.name)) continue
      hit.set(attr.name, attr.value)
    }

    expect(hit.getAttribute('marker-end')).toBeNull()
    expect(hit.getAttribute('stroke')).toBe('#20242A')
    expect(hit.getAttribute('stroke-width')).toBe('1.5')
  })
})
