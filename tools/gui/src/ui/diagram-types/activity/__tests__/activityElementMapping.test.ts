/**
 * Tests for the activity viewer extension's `mapElements`. The fake `<a>` elements below
 * mirror, one-for-one, `fixtures/order-flow.svg` — a real render (PlantUML 1.2026.3, via
 * `plantuml.jar`) of a diagram with one bound action (`entity_id: APC@1.orders`), one unbound
 * action (`a2`), and one decision (`d1`). Regenerate the fixture with
 * `src/diagram_types/activity/renderer.py`'s `ActivityPumlRenderer` + `plantuml.jar -tsvg` if
 * the renderer's emitted link syntax ever changes.
 */
import { describe, it, expect } from 'vitest'
import { activityMapElements } from '../activityElementMapping'
import { FakeElement, FakeSvgRoot, asSvgRoot, makeEntity } from '../../../lib/__tests__/svgDomFakes'

function addSentinelLink(root: FakeSvgRoot, href: string): FakeElement {
  const a = root.appendChild(new FakeElement('a'))
  a.setAttribute('href', href)
  return a
}

describe('activityMapElements', () => {
  it('maps a bound action sentinel to the real model entity it represents', () => {
    const root = new FakeSvgRoot()
    const link = addSentinelLink(root, 'arch://APC@1.orders')

    const { nodes } = activityMapElements(asSvgRoot(root), {
      entities: [makeEntity('APC@1.orders', '', 'application-component')],
      connections: [],
    })
    expect(nodes.get('APC@1.orders')).toEqual([link])
  })

  it('maps an unbound action sentinel via the diagram-local placeholder entity', () => {
    const root = new FakeSvgRoot()
    const link = addSentinelLink(root, 'arch://a2')

    const { nodes } = activityMapElements(asSvgRoot(root), {
      entities: [makeEntity('ACT@1#action/a2', 'a2', 'action')],
      connections: [],
    })
    expect(nodes.get('ACT@1#action/a2')).toEqual([link])
  })

  it('maps a decision sentinel the same way as an action', () => {
    const root = new FakeSvgRoot()
    const link = addSentinelLink(root, 'arch://d1')

    const { nodes } = activityMapElements(asSvgRoot(root), {
      entities: [makeEntity('ACT@1#decision/d1', 'd1', 'decision')],
      connections: [],
    })
    expect(nodes.get('ACT@1#decision/d1')).toEqual([link])
  })

  it('ignores a user-supplied link (non-arch:// href)', () => {
    const root = new FakeSvgRoot()
    addSentinelLink(root, 'https://example.com/docs')

    const { nodes } = activityMapElements(asSvgRoot(root), {
      entities: [makeEntity('APC@1.orders', '', 'application-component')],
      connections: [],
    })
    expect(nodes.size).toBe(0)
  })

  it('returns no edges (activity has no selectable connections)', () => {
    const root = new FakeSvgRoot()
    const { edges } = activityMapElements(asSvgRoot(root), { entities: [], connections: [] })
    expect(edges.size).toBe(0)
  })
})

describe('whole-step selectability (label-wrapped sentinels)', () => {
  // Mirrors the new renderer emission (`:[[arch://id label]];`): PlantUML places the step's
  // rect/polygon as the immediate previous sibling of the label's <a> — see
  // fixtures/order-flow-wrapped.svg for a structurally faithful sample.
  it('includes the action rect so clicking the shape selects the step', () => {
    const root = new FakeSvgRoot()
    const rect = root.appendChild(new FakeElement('rect'))
    const link = addSentinelLink(root, 'arch://APC@1.orders')

    const { nodes } = activityMapElements(asSvgRoot(root), {
      entities: [makeEntity('APC@1.orders', '', 'application-component')],
      connections: [],
    })
    expect(nodes.get('APC@1.orders')).toEqual([rect, link])
  })

  it('includes the decision polygon', () => {
    const root = new FakeSvgRoot()
    const polygon = root.appendChild(new FakeElement('polygon'))
    const link = addSentinelLink(root, 'arch://d1')

    const { nodes } = activityMapElements(asSvgRoot(root), {
      entities: [makeEntity('ACT@1#decision/d1', 'd1', 'decision')],
      connections: [],
    })
    expect(nodes.get('ACT@1#decision/d1')).toEqual([polygon, link])
  })

  it('claims no shape when the previous sibling is not one (old-format SVGs, arrow paths)', () => {
    const root = new FakeSvgRoot()
    root.appendChild(new FakeElement('text'))
    const link = addSentinelLink(root, 'arch://a2')

    const { nodes } = activityMapElements(asSvgRoot(root), {
      entities: [makeEntity('ACT@1#action/a2', 'a2', 'action')],
      connections: [],
    })
    expect(nodes.get('ACT@1#action/a2')).toEqual([link])
  })
})
