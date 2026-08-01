// @vitest-environment jsdom
//
// jsdom is required: these helpers manipulate real SVG DOM elements (style overlay
// application), which a node environment cannot construct.
import { describe, expect, it } from 'vitest'
import {
  ANCHOR_MARKER_COLOR, anchorBadges, applyAnchorMarker, applyEdgeHighlightOverlay,
  applyNodeColorOverlay, centerAnchorsAfterFit, centerDelta, markAnchorEntities,
  markDerivedConnections, projectionByItemId, resolveAnchorElements,
  toDiagramConnectionStub, toEntitySummaryStub, unionRect,
} from '../ViewpointDiagramView.helpers'
import type { ConnectionItemSummary, DiagramConnection, EntityItemSummary, ProjectedOccurrence } from '../../../domain'
import { occurrence } from './projectionFixtures'

const SVG_NS = 'http://www.w3.org/2000/svg'
const svgEl = (tag: string): SVGElement => document.createElementNS(SVG_NS, tag)

const groupWith = (childTag: string): { group: SVGElement; child: SVGElement } => {
  const group = svgEl('g')
  const child = svgEl(childTag)
  group.appendChild(child)
  return { group, child }
}

describe('toEntitySummaryStub', () => {
  const entity: EntityItemSummary = {
    id: 'APC@1.EntSch.a', name: 'Alpha', type: 'application-component',
    specialization_slugs: [], group: 'uncategorized', domain: 'application', membership: 'primary', status: 'draft', version: '1', column_values: null, anchor_modeled_distance: null, matched_via_derived_hops: null,
  }

  it('falls back to the raw artifact id when no alias lookup is given', () => {
    const stub = toEntitySummaryStub(entity)
    expect(stub.artifact_id).toBe('APC@1.EntSch.a')
    expect(stub.display_alias).toBe('APC@1.EntSch.a')
    expect(stub.name).toBe('Alpha')
    expect(stub.artifact_type).toBe('application-component')
  })

  it('resolves display_alias from the given entity_aliases lookup — the rendered SVG PlantUML alias, not the artifact id', () => {
    const aliasById = new Map([['APC@1.EntSch.a', 'JNA_zGOowi']])
    expect(toEntitySummaryStub(entity, aliasById).display_alias).toBe('JNA_zGOowi')
  })
})

describe('toDiagramConnectionStub', () => {
  const conn: ConnectionItemSummary = {
    id: 'c1', type: 'serving', source: 'a', target: 'b', certainty: null, hops: null, via_connection_ids: [], witness_steps: [],
  }

  it('falls back to the raw source/target artifact ids when no alias lookup is given', () => {
    const stub = toDiagramConnectionStub(conn)
    expect(stub.artifact_id).toBe('c1')
    expect(stub.source_alias).toBe('a')
    expect(stub.target_alias).toBe('b')
    expect(stub.conn_type).toBe('serving')
  })

  it('resolves source_alias/target_alias from the given alias lookup', () => {
    const aliasById = new Map([['a', 'ent0042'], ['b', 'ent0099']])
    const stub = toDiagramConnectionStub(conn, new Map(), aliasById)
    expect(stub.source_alias).toBe('ent0042')
    expect(stub.target_alias).toBe('ent0099')
  })

  it('falls back to the raw id when no name lookup is given', () => {
    expect(toDiagramConnectionStub(conn)).toMatchObject({ source_name: 'a', target_name: 'b' })
  })

  it('resolves source_name/target_name from the given lookup', () => {
    const nameById = new Map([['a', 'Alpha'], ['b', 'Beta']])
    expect(toDiagramConnectionStub(conn, nameById)).toMatchObject({ source_name: 'Alpha', target_name: 'Beta' })
  })

  it('carries certainty/hops/via_connection_ids straight through for a derived connection', () => {
    const derived: ConnectionItemSummary = {
      id: 'derived::archimate-serving::x', type: 'archimate-serving', source: 'a', target: 'b',
      certainty: 'potential', hops: 3, via_connection_ids: ['CON@1', 'CON@2', 'CON@3'], witness_steps: [],
    }
    const stub = toDiagramConnectionStub(derived)
    expect(stub.certainty).toBe('potential')
    expect(stub.hops).toBe(3)
    expect(stub.via_connection_ids).toEqual(['CON@1', 'CON@2', 'CON@3'])
  })

  it('carries a real (non-derived) connection\'s null certainty/hops and empty via_connection_ids through unchanged', () => {
    const stub = toDiagramConnectionStub(conn)
    expect(stub.certainty).toBeNull()
    expect(stub.hops).toBeNull()
    expect(stub.via_connection_ids).toEqual([])
  })
})

describe('markDerivedConnections', () => {
  const stubConnection = (overrides: Partial<DiagramConnection>): DiagramConnection => ({
    artifact_id: 'c1', source: 'a', target: 'b', conn_type: 'serving',
    version: '', status: '', path: '', content_text: '', source_name: 'a', target_name: 'b',
    source_alias: null, target_alias: null, certainty: null, hops: null, via_connection_ids: [], ...overrides,
  })

  it('sets data-certainty on the SVG elements matched to a derived connection', () => {
    const { group } = groupWith('path')
    const edges = new Map([['c1', [group]]])
    markDerivedConnections(edges, [stubConnection({ artifact_id: 'c1', certainty: 'potential' })])
    expect(group.getAttribute('data-certainty')).toBe('potential')
  })

  it('leaves a real (non-derived) connection\'s elements untouched', () => {
    const { group } = groupWith('path')
    const edges = new Map([['c1', [group]]])
    markDerivedConnections(edges, [stubConnection({ artifact_id: 'c1', certainty: null })])
    expect(group.hasAttribute('data-certainty')).toBe(false)
  })

  it('ignores an edge whose connection id has no matching entry at all', () => {
    const { group } = groupWith('path')
    const edges = new Map([['unmatched', [group]]])
    markDerivedConnections(edges, [stubConnection({ artifact_id: 'c1', certainty: 'certain' })])
    expect(group.hasAttribute('data-certainty')).toBe(false)
  })
})

describe('applyNodeColorOverlay', () => {
  it('sets an important stroke override on shape children when a token is given', () => {
    const { group, child } = groupWith('rect')
    applyNodeColorOverlay([group], 'critical')
    expect(child.style.getPropertyValue('stroke')).toBe('rgb(220, 38, 38)')
    expect(child.style.getPropertyPriority('stroke')).toBe('important')
    expect(child.style.getPropertyValue('stroke-width')).toBe('3')
  })

  it('never touches the shape\'s native stroke when no token is given — PlantUML relies on it for visibility', () => {
    const { group, child } = groupWith('polygon')
    child.setAttribute('style', 'stroke:#181818;stroke-width:1;')
    applyNodeColorOverlay([group], undefined)
    expect(child.style.getPropertyValue('stroke')).toBe('rgb(24, 24, 24)')
    expect(child.style.getPropertyValue('stroke-width')).toBe('1')
  })

  it('only targets rect/polygon/path descendants, not the group itself', () => {
    const { group } = groupWith('text')
    applyNodeColorOverlay([group], 'critical')
    expect(group.style.getPropertyValue('stroke')).toBe('')
  })

  it('renders an explicit #rrggbb style value as-is (custom colors flow through tokenColor)', () => {
    const { group, child } = groupWith('rect')
    applyNodeColorOverlay([group], '#123abc')
    expect(child.style.getPropertyValue('stroke')).toBe('rgb(18, 58, 188)')
  })
})

describe('applyEdgeHighlightOverlay', () => {
  it('applies color and the token-mapped stroke-width/dash pattern', () => {
    const { group, child } = groupWith('path')
    applyEdgeHighlightOverlay([group], 'caution', 'caution')
    expect(child.style.getPropertyValue('stroke')).toBe('rgb(217, 119, 6)')
    expect(child.style.getPropertyValue('stroke-width')).toBe('2.5')
    expect(child.style.getPropertyValue('stroke-dasharray')).toBe('6 3')
  })

  it('sets no dash pattern when the emphasis token has none', () => {
    const { group, child } = groupWith('path')
    applyEdgeHighlightOverlay([group], undefined, 'emphasis')
    expect(child.style.getPropertyValue('stroke-dasharray')).toBe('')
  })

  it('never touches the shape\'s native stroke when neither color nor emphasis is given — a connector line has no fill and relies entirely on its native stroke for visibility', () => {
    const { group, child } = groupWith('path')
    child.setAttribute('style', 'stroke:#181818;stroke-width:1;')
    applyEdgeHighlightOverlay([group], undefined, undefined)
    expect(child.style.getPropertyValue('stroke')).toBe('rgb(24, 24, 24)')
    expect(child.style.getPropertyValue('stroke-width')).toBe('1')
  })
})

describe('resolveAnchorElements', () => {
  it('collects matched node elements in anchor order', () => {
    const a = groupWith('rect').group
    const b = groupWith('rect').group
    const nodes = new Map<string, readonly Element[]>([['A@1', [a]], ['B@1', [b]]])
    expect(resolveAnchorElements(['B@1', 'A@1'], nodes)).toEqual([b, a])
  })

  it('contributes nothing for an anchor id with no matched SVG element', () => {
    const a = groupWith('rect').group
    const nodes = new Map<string, readonly Element[]>([['A@1', [a]]])
    expect(resolveAnchorElements(['A@1', 'dropped'], nodes)).toEqual([a])
  })

  it('resolves to an empty list when there are no anchors', () => {
    expect(resolveAnchorElements([], new Map())).toEqual([])
  })
})

describe('applyAnchorMarker', () => {
  it('tags the group and inserts a dashed halo clone underneath the body shape', () => {
    const { group, child } = groupWith('rect')
    applyAnchorMarker([group])
    expect(group.getAttribute('data-anchor')).toBe('true')
    const halo = group.firstElementChild as SVGElement
    expect(halo).not.toBe(child)
    expect(halo.tagName).toBe('rect')
    expect(halo.getAttribute('data-anchor-halo')).toBe('true')
    expect(halo.style.getPropertyValue('stroke')).toBe('rgb(124, 58, 237)')
    expect(halo.style.getPropertyPriority('stroke')).toBe('important')
    expect(halo.style.getPropertyValue('stroke-width')).toBe('6')
    expect(halo.style.getPropertyValue('stroke-dasharray')).toBe('8 4')
    expect(halo.style.getPropertyValue('fill')).toBe('none')
    expect(halo.style.getPropertyValue('pointer-events')).toBe('none')
  })

  it('halos only the first (body) shape, not every decorative shape child', () => {
    const { group } = groupWith('rect')
    group.appendChild(svgEl('path'))
    applyAnchorMarker([group])
    expect(group.querySelectorAll('[data-anchor-halo]')).toHaveLength(1)
  })

  it('composes with a node_color overlay: the body keeps the overlay stroke, the halo keeps the anchor accent', () => {
    const { group, child } = groupWith('rect')
    applyNodeColorOverlay([group], 'critical')
    applyAnchorMarker([group])
    expect(child.style.getPropertyValue('stroke')).toBe('rgb(220, 38, 38)')
    const halo = group.querySelector('[data-anchor-halo]') as SVGElement
    expect(halo.style.getPropertyValue('stroke')).toBe('rgb(124, 58, 237)')
  })

  it('never stacks a second halo when applied again to the same group', () => {
    const { group } = groupWith('rect')
    applyAnchorMarker([group])
    applyAnchorMarker([group])
    expect(group.querySelectorAll('[data-anchor-halo]')).toHaveLength(1)
  })

  it('tags a group with no shape children without inserting a halo', () => {
    const { group } = groupWith('text')
    applyAnchorMarker([group])
    expect(group.getAttribute('data-anchor')).toBe('true')
    expect(group.querySelectorAll('[data-anchor-halo]')).toHaveLength(0)
  })

  it('uses an accent outside the style-token palette', () => {
    expect(ANCHOR_MARKER_COLOR).toBe('#7c3aed')
  })
})

describe('anchorBadges', () => {
  const entity = (id: string, name: string): EntityItemSummary => ({
    id, name, type: 'application-component',
    specialization_slugs: [], group: 'uncategorized', domain: 'application', membership: 'primary', status: 'draft', version: '1', column_values: null, anchor_modeled_distance: null, matched_via_derived_hops: null,
  })

  it('resolves each anchor id to its entity name', () => {
    const badges = anchorBadges(['A@1'], [entity('A@1', 'Alpha'), entity('B@1', 'Beta')])
    expect(badges).toEqual([{ id: 'A@1', name: 'Alpha' }])
  })

  it('falls back to the raw id when the entity is absent from the population', () => {
    expect(anchorBadges(['gone'], [])).toEqual([{ id: 'gone', name: 'gone' }])
  })
})

describe('unionRect', () => {
  it('is null for an empty list', () => {
    expect(unionRect([])).toBeNull()
  })

  it('covers all input rects', () => {
    const union = unionRect([
      { left: 10, top: 20, width: 30, height: 10 },
      { left: 0, top: 25, width: 15, height: 40 },
    ])
    expect(union).toEqual({ left: 0, top: 20, width: 40, height: 45 })
  })
})

describe('markAnchorEntities', () => {
  it('marks the matched elements and returns them for centering', () => {
    const { group } = groupWith('rect')
    const marked = markAnchorEntities(['A@1'], new Map([['A@1', [group]]]))
    expect(marked).toEqual([group])
    expect(group.getAttribute('data-anchor')).toBe('true')
    expect(group.querySelectorAll('[data-anchor-halo]')).toHaveLength(1)
  })

  it('marks nothing and returns an empty list without anchors', () => {
    const { group } = groupWith('rect')
    expect(markAnchorEntities([], new Map([['A@1', [group]]]))).toEqual([])
    expect(group.hasAttribute('data-anchor')).toBe(false)
  })
})

describe('centerAnchorsAfterFit', () => {
  const withRect = (left: number, top: number, width: number, height: number): Element => {
    const el = svgEl('g')
    el.getBoundingClientRect = () => ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) })
    return el
  }

  it('fits first, then pans the anchor union center onto the container center', async () => {
    const calls: string[] = []
    const container = withRect(0, 0, 800, 600)
    const anchor = withRect(500, 100, 100, 50)
    let panned: readonly [number, number] | null = null
    const fit = () => { calls.push('fit'); return Promise.resolve() }
    await centerAnchorsAfterFit([anchor], container, fit, (dx, dy) => {
      calls.push('pan')
      panned = [dx, dy]
    })
    expect(calls).toEqual(['fit', 'pan'])
    expect(panned).toEqual([-150, 175])
  })

  it('never fits or pans when there is no anchor element', async () => {
    const calls: string[] = []
    const fit = () => { calls.push('fit'); return Promise.resolve() }
    await centerAnchorsAfterFit([], withRect(0, 0, 800, 600), fit, () => calls.push('pan'))
    expect(calls).toEqual([])
  })

  it('never fits or pans when the container is not mounted', async () => {
    const calls: string[] = []
    const fit = () => { calls.push('fit'); return Promise.resolve() }
    await centerAnchorsAfterFit([withRect(0, 0, 10, 10)], null, fit, () => calls.push('pan'))
    expect(calls).toEqual([])
  })
})

describe('centerDelta', () => {
  it('moves the target center onto the viewport center', () => {
    const viewport = { left: 0, top: 0, width: 800, height: 600 }
    const target = { left: 500, top: 100, width: 100, height: 50 }
    expect(centerDelta(viewport, target)).toEqual({ dx: -150, dy: 175 })
  })

  it('is zero when the target is already centered', () => {
    const viewport = { left: 100, top: 50, width: 200, height: 100 }
    const target = { left: 190, top: 95, width: 20, height: 10 }
    expect(centerDelta(viewport, target)).toEqual({ dx: 0, dy: 0 })
  })
})

describe('projectionByItemId', () => {
  it('indexes projected occurrences by item id', () => {
    const items: ProjectedOccurrence[] = [occurrence({ item_id: 'a', style: { node_color: 'positive' } })]
    expect(projectionByItemId(items).get('a')?.style.node_color).toBe('positive')
  })
})
