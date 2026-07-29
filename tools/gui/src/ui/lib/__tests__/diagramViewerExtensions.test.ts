/**
 * Contract tests for `resolveElementMap`: a registered extension's `mapElements` wins when
 * present; otherwise the generic viewer falls back to the graphviz/PlantUML default matcher
 * (WU-A4's `DiagramViewerExtension.mapElements`, decision D-3). No jsdom/happy-dom in this
 * project (see `svgHitAreas.test.ts`) — a minimal fake element stands in for the SVG root.
 */
import { describe, it, expect } from 'vitest'
import {
  registerViewerExtension,
  resolveElementMap,
  type DiagramElementMap,
} from '../diagramViewerExtensions'
import type { EntitySummary } from '../../../domain'

class FakeElement {
  private attrs = new Map<string, string>()
  constructor(public tagName: string, public id = '') {}
  setAttribute(name: string, value: string): void { this.attrs.set(name, value) }
  getAttribute(name: string): string | null { return this.attrs.get(name) ?? null }
  hasAttribute(name: string): boolean { return this.attrs.has(name) }
}

class FakeSvgRoot {
  private nodes: FakeElement[] = []
  addNode(node: FakeElement): FakeElement { this.nodes.push(node); return node }
  querySelectorAll(selector: string): FakeElement[] {
    if (selector === 'g') return this.nodes
    if (selector === 'g[data-entity-1]') return this.nodes.filter((n) => n.hasAttribute('data-entity-1'))
    throw new Error(`unsupported selector: ${selector}`)
  }
  getElementById(): FakeElement | null { return null }
}

const makeEntity = (id: string, alias: string): EntitySummary => ({
  artifact_id: id,
  artifact_type: 'application-component',
  name: id,
  version: '0.1.0',
  status: 'active',
  domain: 'application',
  subdomain: '',
  path: '/tmp/x.md',
  is_global: false,
  group: 'uncategorized',
  display_alias: alias,
})

const untouchableSvgRoot = () => new Proxy({}, {
  get(_target, prop) {
    throw new Error(`unexpected access: ${String(prop)}`)
  },
}) as unknown as SVGSVGElement

describe('resolveElementMap', () => {
  it('uses the registered extension\'s mapElements when present, without touching the SVG itself', () => {
    const stubResult: DiagramElementMap = {
      nodes: new Map([['ENT@1', []]]),
      edges: new Map(),
    }
    registerViewerExtension('contract-test-with-map', {
      attachNodeSubParts: () => {},
      detailComponent: {} as never,
      mapElements: () => stubResult,
    })

    const result = resolveElementMap('contract-test-with-map', untouchableSvgRoot(), {
      entities: [],
      connections: [],
    })
    expect(result).toBe(stubResult)
  })

  it('falls back to the graphviz default when the extension declares no mapElements', () => {
    registerViewerExtension('contract-test-without-map', {
      attachNodeSubParts: () => {},
      detailComponent: {} as never,
    })

    const root = new FakeSvgRoot()
    const g = root.addNode(new FakeElement('g'))
    g.setAttribute('data-entity', 'MyAlias')

    const result = resolveElementMap(
      'contract-test-without-map',
      root as unknown as SVGSVGElement,
      { entities: [makeEntity('APP@1.x', 'MyAlias')], connections: [] },
    )
    expect(result.nodes.get('APP@1.x')).toEqual([g])
  })

  it('falls back to the graphviz default for an unregistered diagram type', () => {
    const root = new FakeSvgRoot()
    const g = root.addNode(new FakeElement('g'))
    g.setAttribute('data-entity', 'MyAlias')

    const result = resolveElementMap(
      'no-such-type',
      root as unknown as SVGSVGElement,
      { entities: [makeEntity('APP@1.x', 'MyAlias')], connections: [] },
    )
    expect(result.nodes.get('APP@1.x')).toEqual([g])
  })
})
