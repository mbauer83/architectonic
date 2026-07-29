import { describe, it, expect } from 'vitest'
import {
  groupKeyFor, nodeVisualFor, edgeVisualFor, projectionByItemId, edgeStyleKey, buildConnectionStyleIndex, buildConnectionSummaryIndex, DERIVED_EDGE_DASH, explorationRedirectFor, anchorDistancesFromResult, effectiveExplorationLayout, distanceColor, distanceLegend,
  effectiveExplorationFill,
} from '../GraphExploreView.helpers'
import { tokenColor, tokenShape, tokenIconLetter, tokenEdgeEmphasis, resolveStyleColor } from '../../lib/viewpointStyleTokens'
import type { ViewpointDefinitionEnvelope } from '../../../domain'

const mkEnvelope = (representation: string | null): ViewpointDefinitionEnvelope => ({
  slug: 'application-structure', version: 1, name: 'Application Structure', tier: 'module',
  scope_summary: { unrestricted: true }, query_summary: null, fork_status: null,
  presentation: representation === null ? undefined : { representation },
})

const entity = {
  type: 'application-component', group: 'core', specialization_slugs: ['custom-spec'],
  domain: 'application',
}

describe('groupKeyFor', () => {
  it('groups by domain when group_by is "domain"', () => {
    // A declared dimension must resolve here. Falling through to the type default would
    // group by something the definition did not ask for, and would silently disable the
    // layered ordering that grouping by domain exists to enable.
    expect(groupKeyFor(entity, 'domain')).toBe('application')
  })

  it('falls back to "unknown" for an entity with no domain', () => {
    expect(groupKeyFor({ ...entity, domain: '' }, 'domain')).toBe('unknown')
  })

  it('groups by group when group_by is "group"', () => {
    expect(groupKeyFor(entity, 'group')).toBe('core')
  })

  it('groups by first specialization slug when group_by is "specialization"', () => {
    expect(groupKeyFor(entity, 'specialization')).toBe('custom-spec')
  })

  it('falls back to "(none)" when specialization requested but absent', () => {
    expect(groupKeyFor({ ...entity, specialization_slugs: [] }, 'specialization')).toBe('(none)')
  })

  it('groups by type for "type", null, and any unresolvable attribute path', () => {
    expect(groupKeyFor(entity, 'type')).toBe('application-component')
    expect(groupKeyFor(entity, null)).toBe('application-component')
    expect(groupKeyFor(entity, 'some.custom.attribute')).toBe('application-component')
  })
})

describe('nodeVisualFor', () => {
  it('falls back to the domain color and default shape/icon when unstyled; no glyph without a type', () => {
    expect(nodeVisualFor(undefined, '#abcabc')).toEqual({
      color: '#abcabc', shape: 'circle', iconLetter: null, glyph: null,
    })
  })

  it('resolves node_color/node_shape/node_icon from the style map', () => {
    const visual = nodeVisualFor({ node_color: 'critical', node_shape: 'critical', node_icon: 'critical' }, '#abcabc')
    expect(visual).toEqual({
      color: tokenColor('critical'), shape: tokenShape('critical'), iconLetter: tokenIconLetter('critical'), glyph: null,
    })
  })

  it('resolves the ArchiMate glyph from the artifact type', () => {
    expect(nodeVisualFor(undefined, '#abcabc', 'stakeholder').glyph).toBeTruthy()
  })
})

describe('edgeVisualFor', () => {
  it('returns all-null (default edge rendering) when unstyled', () => {
    // With no notation either, the edge falls back to the plain directed line the canvas has
    // always drawn — an unstyled edge must not become invisible.
    expect(edgeVisualFor(undefined)).toEqual({
      stroke: null, strokeWidth: null, dashArray: undefined,
      sourceMarker: 'none', targetMarker: 'filled-arrow',
    })
  })

  it('resolves edge_color/edge_emphasis from the style map', () => {
    const visual = edgeVisualFor({ edge_color: 'caution', edge_emphasis: 'caution' })
    const emphasis = tokenEdgeEmphasis('caution')
    expect(visual).toEqual({
      stroke: tokenColor('caution'), strokeWidth: emphasis.strokeWidth,
      dashArray: emphasis.dashArray, sourceMarker: 'none', targetMarker: 'filled-arrow',
    })
  })

  it('resolves edge_color independently of edge_emphasis', () => {
    expect(edgeVisualFor({ edge_color: 'positive' })).toEqual({
      stroke: tokenColor('positive'), strokeWidth: null, dashArray: undefined,
      sourceMarker: 'none', targetMarker: 'filled-arrow',
    })
  })

  it('gives an unstyled derived edge its provenance dash, denser for potential', () => {
    expect(edgeVisualFor(undefined, 'certain').dashArray).toBe(DERIVED_EDGE_DASH.certain)
    expect(edgeVisualFor(undefined, 'potential').dashArray).toBe(DERIVED_EDGE_DASH.potential)
    expect(DERIVED_EDGE_DASH.certain).not.toBe(DERIVED_EDGE_DASH.potential)
  })

  it('lets an authored edge_emphasis dash win over the provenance dash', () => {
    const emphasis = tokenEdgeEmphasis('caution')
    expect(edgeVisualFor({ edge_emphasis: 'caution' }, 'certain').dashArray).toBe(emphasis.dashArray)
  })
})

describe('buildConnectionSummaryIndex', () => {
  it('joins each connection summary onto its source/target/type key', () => {
    const derived = {
      id: 'derived::x', type: 'archimate-serving', source: 'ENT@A', target: 'ENT@B',
      certainty: 'certain' as const, hops: 2, via_connection_ids: ['c1', 'c2'], witness_steps: [],
    }
    const index = buildConnectionSummaryIndex([derived])
    expect(index.get(edgeStyleKey('ENT@A', 'ENT@B', 'archimate-serving'))?.hops).toBe(2)
  })
})

describe('projectionByItemId', () => {
  it('indexes items by item_id', () => {
    const projection = {
      applied: true, target: 'repository' as const,
      items: [
        { item_id: 'ENT@A', item_kind: 'entity' as const, state: 'visible' as const, membership: 'primary' as const, reasons: [], style: { node_color: 'positive' } },
      ],
    }
    const byId = projectionByItemId(projection)
    expect(byId.get('ENT@A')?.style).toEqual({ node_color: 'positive' })
  })

  it('returns an empty map for a null projection', () => {
    expect(projectionByItemId(null).size).toBe(0)
  })
})

describe('buildConnectionStyleIndex', () => {
  it('joins a connection style back onto its source/target/type key', () => {
    const connections = [{ id: 'CON@ab', type: 'archimate-serving', source: 'ENT@A', target: 'ENT@B', certainty: null, hops: null, via_connection_ids: [], witness_steps: [] }]
    const projection = {
      applied: true, target: 'repository' as const,
      items: [
        {
          item_id: 'CON@ab', item_kind: 'connection' as const, state: 'visible' as const,
          membership: 'primary' as const, reasons: [], style: { edge_color: 'critical' },
        },
      ],
    }
    const index = buildConnectionStyleIndex(connections, projection)
    expect(index.get(edgeStyleKey('ENT@A', 'ENT@B', 'archimate-serving'))).toEqual({ edge_color: 'critical' })
  })

  it('omits connections absent from the projection', () => {
    const connections = [{ id: 'CON@ab', type: 'archimate-serving', source: 'ENT@A', target: 'ENT@B', certainty: null, hops: null, via_connection_ids: [], witness_steps: [] }]
    expect(buildConnectionStyleIndex(connections, null).size).toBe(0)
  })
})

describe('explorationRedirectFor', () => {
  it('stays put (returns null) for an exploration-representation definition', () => {
    expect(explorationRedirectFor(mkEnvelope('exploration'))).toBeNull()
  })

  it('stays put when the definition carries no presentation at all', () => {
    expect(explorationRedirectFor(mkEnvelope(null))).toBeNull()
  })

  it('redirects to the diagram surface for a diagram-representation definition', () => {
    expect(explorationRedirectFor(mkEnvelope('diagram'))).toEqual({
      path: '/viewpoints/diagram', query: { viewpoint: 'application-structure' },
    })
  })

  it('redirects to the matrix/table surfaces for matrix/table representations', () => {
    expect(explorationRedirectFor(mkEnvelope('matrix'))?.path).toBe('/viewpoints/matrix')
    expect(explorationRedirectFor(mkEnvelope('table'))?.path).toBe('/entities')
  })

  it('stays put when no envelope was found for the selected slug', () => {
    expect(explorationRedirectFor(undefined)).toBeNull()
  })
})

describe('anchorDistancesFromResult', () => {
  it('maps each ranked entity to its server-computed modeled distance', () => {
    const distances = anchorDistancesFromResult([
      { id: 'a', anchor_modeled_distance: 0 },
      { id: 'b', anchor_modeled_distance: 1 },
      { id: 'c', anchor_modeled_distance: 4 }, // witness-chain length, NOT one traversal step
    ])
    expect(distances.get('a')).toBe(0)
    expect(distances.get('b')).toBe(1)
    expect(distances.get('c')).toBe(4)
  })

  it('leaves unranked entities out of the map instead of defaulting them', () => {
    const distances = anchorDistancesFromResult([
      { id: 'a', anchor_modeled_distance: 0 },
      { id: 'island', anchor_modeled_distance: null },
      { id: 'legacy' },
    ])
    expect(distances.has('island')).toBe(false)
    expect(distances.has('legacy')).toBe(false)
    expect(distances.size).toBe(1)
  })
})

describe('effectiveExplorationLayout', () => {
  it('lets an explicit user override win over everything', () => {
    expect(effectiveExplorationLayout('force', 'radial', true)).toBe('force')
    expect(effectiveExplorationLayout('clusters', undefined, true)).toBe('clusters')
  })

  it('uses the definition display option when the override is auto', () => {
    expect(effectiveExplorationLayout('auto', 'force', true)).toBe('force')
    expect(effectiveExplorationLayout('auto', 'clusters', true)).toBe('clusters')
  })

  it('ignores an unknown or absent display option', () => {
    expect(effectiveExplorationLayout('auto', 'spiral', false)).toBe('clusters')
    expect(effectiveExplorationLayout('auto', undefined, false)).toBe('clusters')
  })

  it('defaults an anchored execution to radial and an unanchored one to clusters', () => {
    expect(effectiveExplorationLayout('auto', undefined, true)).toBe('radial')
    expect(effectiveExplorationLayout('auto', undefined, false)).toBe('clusters')
  })
})

describe('distanceColor', () => {
  it('maps depth 0 to the near endpoint and max depth to the far endpoint', () => {
    expect(distanceColor(0, 4)).toBe(tokenColor('heat-near'))
    expect(distanceColor(4, 4)).toBe(tokenColor('heat-far'))
  })

  it('uses the near endpoint when everything is at depth 0', () => {
    expect(distanceColor(0, 0)).toBe(tokenColor('heat-near'))
  })

  it('interpolates intermediate depths on the heat-near→heat-far scale', () => {
    expect(distanceColor(1, 2)).toBe(resolveStyleColor({ position: 0.5, tokens: ['heat-near', 'heat-far'] }))
    expect(distanceColor(1, 2)).not.toBe(tokenColor('heat-near'))
    expect(distanceColor(1, 2)).not.toBe(tokenColor('heat-far'))
  })
})

describe('distanceLegend', () => {
  it('shows the real observed ring set, not a dense 0..max range', () => {
    const legend = distanceLegend([0, 1, 2, 4, 2, 1])
    expect(legend.map((entry) => entry.label)).toEqual(['1 hop', '2 hops', '4 hops'])
    expect(legend[2].color).toBe(tokenColor('heat-far'))
    expect(legend[0].color).toBe(distanceColor(1, 4))
    expect(legend[1].color).toBe(distanceColor(2, 4))
  })

  it('omits the anchor distance (0) — the Anchor chip already names it', () => {
    expect(distanceLegend([0])).toEqual([])
  })

  it('is empty for no observed distances', () => {
    expect(distanceLegend([])).toEqual([])
  })
})

describe('effectiveExplorationFill', () => {
  it('colours by domain when the presentation says nothing', () => {
    expect(effectiveExplorationFill(undefined, 4)).toBe('domain')
  })

  it('does not switch to hop distance merely because a query is anchored', () => {
    // Anchoring is a reachability choice. A definition must not change how it looks
    // because it started taking a parameter.
    expect(effectiveExplorationFill(undefined, 1)).toBe('domain')
    expect(effectiveExplorationFill('domain', 4)).toBe('domain')
  })

  it('honours an explicit hop-distance request when there is a range to show', () => {
    expect(effectiveExplorationFill('hop-distance', 4)).toBe('hop-distance')
  })

  it('falls back to domain when every neighbour is one hop away', () => {
    // A spectrum over a single band paints every node identically and discards the one
    // distinction still worth seeing at that size.
    expect(effectiveExplorationFill('hop-distance', 1)).toBe('domain')
    expect(effectiveExplorationFill('hop-distance', 0)).toBe('domain')
  })

  it('ignores an unrecognised value rather than guessing', () => {
    expect(effectiveExplorationFill('by-vibes', 4)).toBe('domain')
  })
})

describe('edgeVisualFor with a relationship notation', () => {
  /*
   * The graph drew every ArchiMate relationship as one solid line with a filled head, so a
   * composition, a realization and an association were indistinguishable. The notation comes
   * from the ontology; these hold that it reaches the canvas, and that the two things which
   * legitimately outrank it still do.
   */
  const composition = { line: 'solid', source: 'filled-diamond', target: 'none' } as const
  const realization = { line: 'dotted', source: 'none', target: 'hollow-triangle' } as const

  it('carries the markers the relationship declares to each end', () => {
    const visual = edgeVisualFor(undefined, null, composition)

    expect(visual.sourceMarker).toBe('filled-diamond')
    expect(visual.targetMarker).toBe('none')
  })

  it('turns a dotted or dashed line into a dash pattern, and solid into none', () => {
    expect(edgeVisualFor(undefined, null, realization).dashArray).toBeDefined()
    expect(edgeVisualFor(undefined, null, composition).dashArray).toBeUndefined()
  })

  it('renders relationships that differ in the ontology differently', () => {
    // The blanket property: whatever the shapes are, two distinct notations must not collapse
    // into one visual — which is precisely what the defect was.
    expect(edgeVisualFor(undefined, null, composition))
      .not.toEqual(edgeVisualFor(undefined, null, realization))
  })

  it('lets a viewpoint emphasis outrank the notation line', () => {
    // A viewpoint styling an edge is making a statement about this view; the notation is a
    // statement about the relationship type. The more specific one wins.
    const emphasis = tokenEdgeEmphasis('caution')

    expect(edgeVisualFor({ edge_emphasis: 'caution' }, null, realization).dashArray)
      .toBe(emphasis.dashArray)
  })

  it('lets derivation provenance outrank the notation line', () => {
    // "This edge was inferred" is not something a relationship type can say about itself.
    expect(edgeVisualFor(undefined, 'potential', realization).dashArray)
      .toBe(DERIVED_EDGE_DASH.potential)
  })

  it('still keeps the notation markers when the line is overridden', () => {
    // Only the line is contested; the head is the relationship's own and survives.
    expect(edgeVisualFor(undefined, 'potential', realization).targetMarker)
      .toBe('hollow-triangle')
  })
})
