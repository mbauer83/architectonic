/**
 * Contract tests for the graphviz/PlantUML default `mapElements` implementation (WU-A4's
 * `DiagramViewerExtension.mapElements`). No jsdom/happy-dom in this project (see
 * `svgHitAreas.test.ts`) — a minimal fake element tree stands in for the small slice of the DOM
 * API the matcher actually calls (`querySelectorAll('g'|'g[data-entity-1]')`, `getElementById`,
 * `closest('g')`, `querySelector(':scope > title')`).
 */
import { describe, it, expect } from 'vitest'
import { graphvizMapElements } from '../graphvizElementMapping'
import type { DiagramConnection } from '../../../domain'
import { FakeElement, FakeSvgRoot, asSvgRoot, makeEntity } from './svgDomFakes'

const makeConn = (sourceAlias: string, targetAlias: string, id: string): DiagramConnection => ({
  artifact_id: id,
  conn_type: 'flow',
  source: sourceAlias,
  target: targetAlias,
  source_alias: sourceAlias,
  target_alias: targetAlias,
  source_name: sourceAlias,
  target_name: targetAlias,
  content_text: '',
  version: '0.1.0',
  status: 'active',
  path: '/tmp/x.md',
  edge_label_override: null,
  edge_key: null,
})

describe('graphvizMapElements — nodes', () => {
  it('maps a node via data-entity attribute', () => {
    const root = new FakeSvgRoot()
    const g = root.appendChild(new FakeElement('g'))
    g.setAttribute('data-entity', 'MyAlias')
    const { nodes } = graphvizMapElements(asSvgRoot(root), {
      entities: [makeEntity('APP@1.x', 'MyAlias')],
      connections: [],
    })
    expect(nodes.get('APP@1.x')).toEqual([g])
  })

  it('maps a node via entity_<alias> id convention', () => {
    const root = new FakeSvgRoot()
    const g = root.appendChild(new FakeElement('g').setId('entity_MyAlias'))
    const { nodes } = graphvizMapElements(asSvgRoot(root), {
      entities: [makeEntity('APP@1.x', 'MyAlias')],
      connections: [],
    })
    expect(nodes.get('APP@1.x')).toEqual([g])
  })

  it('maps multiple SVG elements to one artifact id (one-to-many, WU-B3 forward-compat)', () => {
    const root = new FakeSvgRoot()
    const g1 = root.appendChild(new FakeElement('g'))
    g1.setAttribute('data-entity', 'MyAlias')
    const g2 = root.appendChild(new FakeElement('g'))
    g2.setAttribute('data-entity', 'MyAlias')
    const { nodes } = graphvizMapElements(asSvgRoot(root), {
      entities: [makeEntity('APP@1.x', 'MyAlias')],
      connections: [],
    })
    expect(nodes.get('APP@1.x')).toEqual([g1, g2])
  })

  it('maps ArchiMate occurrence aliases back to the backing entity', () => {
    const root = new FakeSvgRoot()
    const primary = root.appendChild(new FakeElement('g'))
    primary.setAttribute('data-entity', 'APP_A')
    const second = root.appendChild(new FakeElement('g'))
    second.setAttribute('data-entity', 'APP_A__2')
    const third = root.appendChild(new FakeElement('g'))
    third.setAttribute('data-entity', 'APP_A__3')

    const { nodes } = graphvizMapElements(asSvgRoot(root), {
      entities: [makeEntity('APP@1.a', 'APP_A')],
      connections: [],
      diagramEntities: {
        occurrence: [
          { id: 'occ-app-a-2', backing_entity_id: 'APP@1.a' },
          { id: 'occ-app-a-3', backing_entity_id: 'APP@1.a' },
        ],
      },
    })

    expect(nodes.get('APP@1.a')).toEqual([primary, second, third])
  })

  it('returns empty maps when there are no entities or connections', () => {
    const root = new FakeSvgRoot()
    const { nodes, edges } = graphvizMapElements(asSvgRoot(root), { entities: [], connections: [] })
    expect(nodes.size).toBe(0)
    expect(edges.size).toBe(0)
  })
})

describe('graphvizMapElements — edges', () => {
  it('maps an edge via data-entity-1/data-entity-2 node-id attributes', () => {
    const root = new FakeSvgRoot()
    const gA = root.appendChild(new FakeElement('g').setId('nodeA'))
    gA.setAttribute('data-entity', 'A')
    const gB = root.appendChild(new FakeElement('g').setId('nodeB'))
    gB.setAttribute('data-entity', 'B')
    const gEdge = root.appendChild(new FakeElement('g'))
    gEdge.setAttribute('data-entity-1', 'nodeA')
    gEdge.setAttribute('data-entity-2', 'nodeB')

    const { edges } = graphvizMapElements(asSvgRoot(root), {
      entities: [makeEntity('APP@1.a', 'A'), makeEntity('APP@2.b', 'B')],
      connections: [makeConn('A', 'B', 'CONN@1')],
    })
    expect(edges.get('CONN@1')).toEqual([gEdge])
  })

  it('maps an edge via the link_SOURCE_TARGET id fallback', () => {
    const root = new FakeSvgRoot()
    const gEdge = root.appendChild(new FakeElement('g').setId('link_A_B'))
    const { edges } = graphvizMapElements(asSvgRoot(root), {
      entities: [],
      connections: [makeConn('A', 'B', 'CONN@1')],
    })
    expect(edges.get('CONN@1')).toEqual([gEdge])
  })

  it('maps an edge via the SOURCE-TARGET path-id convention using closest("g")', () => {
    const root = new FakeSvgRoot()
    const gEdge = root.appendChild(new FakeElement('g'))
    const path = gEdge.appendChild(new FakeElement('path').setId('A-B'))
    const { edges } = graphvizMapElements(asSvgRoot(root), {
      entities: [],
      connections: [makeConn('A', 'B', 'CONN@1')],
    })
    expect(edges.get('CONN@1')).toEqual([gEdge])
    expect(path.id).toBe('A-B') // sanity: the path itself is never returned, only its <g>
  })

  it('does not double-count an edge group matched by both the attribute and id conventions', () => {
    const root = new FakeSvgRoot()
    const gA = root.appendChild(new FakeElement('g').setId('nodeA'))
    gA.setAttribute('data-entity', 'A')
    const gB = root.appendChild(new FakeElement('g').setId('nodeB'))
    gB.setAttribute('data-entity', 'B')
    const gEdge = root.appendChild(new FakeElement('g').setId('link_A_B'))
    gEdge.setAttribute('data-entity-1', 'nodeA')
    gEdge.setAttribute('data-entity-2', 'nodeB')

    const { edges } = graphvizMapElements(asSvgRoot(root), {
      entities: [makeEntity('APP@1.a', 'A'), makeEntity('APP@2.b', 'B')],
      connections: [makeConn('A', 'B', 'CONN@1')],
    })
    expect(edges.get('CONN@1')).toEqual([gEdge])
  })
})
