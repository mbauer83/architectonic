import { describe, expect, it } from 'vitest'
import {
  excludedCount,
  facetOptions,
  isExcluded,
  narrowed,
  valuesAt,
  type ClassificationLevel,
  type ClassificationLevels,
} from '../graphFacets'

/**
 * The filter reads a level's value through the level's declared `source`, never through its `id`.
 *
 * Every assertion here that could be written against ArchiMate's chain is written against a second
 * one as well. `archimate-4-0` names its entity levels `domain`, `entity_type` and `specialization`;
 * a filter keyed on those names passes every test against the only meta-ontology that declares them
 * and is ArchiMate-shaped by construction. The requirement is that another meta-ontology, declaring
 * its own chain, works **with no code changes**, and the only way to show that is to run the same
 * assertions through a chain that shares no level id with ArchiMate's.
 */

const ARCHIMATE: ClassificationLevels = {
  entity: [
    { id: 'domain', label: 'Domain', source: 'hierarchy', required: true },
    { id: 'entity_type', label: 'Entity type', source: 'type', required: true },
    { id: 'specialization', label: 'Specialization', source: 'specializations', required: false },
  ],
  relation: [
    { id: 'connection_type', label: 'Relationship type', source: 'type', required: true },
    {
      id: 'connection_specialization',
      label: 'Specialization',
      source: 'specializations',
      required: false,
    },
  ],
}

/** A different meta-ontology: different ids, different labels, a two-level entity chain. */
const OTHER: ClassificationLevels = {
  entity: [
    { id: 'tier', label: 'Tier', source: 'hierarchy', required: true },
    { id: 'kind', label: 'Kind', source: 'type', required: true },
  ],
  relation: [{ id: 'link_kind', label: 'Link kind', source: 'type', required: true }],
}

const node = (
  id: string,
  domain: string,
  artifactType: string,
  specializations: readonly string[] = [],
) => ({ id, domain, artifactType, specializations })

const edge = (
  source: string,
  target: string,
  connType: string,
  specializations: readonly string[] = [],
) => ({ source, target, connType, specializations })

const NODES = [
  node('GOL@1', 'motivation', 'goal', ['strategic']),
  node('GOL@2', 'motivation', 'goal'),
  node('APP@1', 'application', 'application-component'),
]
const EDGES = [
  edge('GOL@1', 'GOL@2', 'archimate-aggregation'),
  edge('APP@1', 'GOL@1', 'archimate-realization', ['partial']),
]

describe('a level names where its values come from, not what they are called', () => {
  it.each([
    ['hierarchy', ['motivation']],
    ['type', ['goal']],
    ['specializations', ['strategic']],
  ])('reads a node value through source %s', (source, expected) => {
    expect(valuesAt(source, NODES[0])).toEqual(expected)
  })

  it('reads an edge type through the same source name a node type uses', () => {
    expect(valuesAt('type', EDGES[0])).toEqual(['archimate-aggregation'])
  })

  it('offers nothing for a source it cannot read, rather than throwing', () => {
    // A meta-ontology may declare a source this client has no way to read. Failing the whole
    // graph over one unreadable level would make a new declaration a breaking change.
    expect(valuesAt('phase-of-the-moon', NODES[0])).toEqual([])
  })

  it('offers nothing where the thing has no value, which is what an optional level means', () => {
    expect(valuesAt('specializations', NODES[1])).toEqual([])
  })
})

describe('only what the loaded graph actually contains is offered', () => {
  it('lists each declared level with the values present, in display order', () => {
    expect(facetOptions(ARCHIMATE.entity, NODES)).toEqual([
      { level: ARCHIMATE.entity[0], values: ['application', 'motivation'] },
      { level: ARCHIMATE.entity[1], values: ['application-component', 'goal'] },
      { level: ARCHIMATE.entity[2], values: ['strategic'] },
    ])
  })

  it('drops a level nothing in this graph has a value for', () => {
    const withoutSpecializations = [node('GOL@2', 'motivation', 'goal')]

    expect(facetOptions(ARCHIMATE.entity, withoutSpecializations).map((o) => o.level.id)).toEqual([
      'domain',
      'entity_type',
    ])
  })

  it('offers the other meta-ontology its own levels, by its own names', () => {
    expect(facetOptions(OTHER.entity, NODES)).toEqual([
      { level: OTHER.entity[0], values: ['application', 'motivation'] },
      { level: OTHER.entity[1], values: ['application-component', 'goal'] },
    ])
  })
})

describe('what a selection hides', () => {
  it('hides a thing excluded at any level', () => {
    expect(isExcluded({ domain: ['motivation'] }, ARCHIMATE.entity, NODES[0])).toBe(true)
    expect(isExcluded({ domain: ['motivation'] }, ARCHIMATE.entity, NODES[2])).toBe(false)
  })

  it('cannot hide a thing through a level it has no value at', () => {
    // Otherwise excluding one specialization hides every element that has none, which reads as
    // the filter being broken rather than as filtering.
    expect(isExcluded({ specialization: ['strategic'] }, ARCHIMATE.entity, NODES[1])).toBe(false)
  })

  it('excludes nothing for a level with an empty exclusion list', () => {
    expect(isExcluded({ domain: [] }, ARCHIMATE.entity, NODES[0])).toBe(false)
  })

  it('counts every excluded value for the headline', () => {
    expect(excludedCount({ domain: ['motivation'], entity_type: ['goal', 'outcome'] })).toBe(3)
    expect(excludedCount({})).toBe(0)
  })
})

describe('narrowing the graph', () => {
  it('drops an edge whose endpoint is gone, not only one excluded itself', () => {
    const result = narrowed(ARCHIMATE, { domain: ['application'] }, NODES, EDGES)

    expect(result.nodes.map((n) => n.id)).toEqual(['GOL@1', 'GOL@2'])
    // APP@1 -> GOL@1 goes with APP@1: an edge to a node that is not drawn is a line to nowhere.
    expect(result.edges).toEqual([EDGES[0]])
    // GOL@1 loses that realization and keeps the aggregation, so it is not stranded.
    expect(result.nodes.map((n) => n.id)).toContain('GOL@1')
  })

  it('drops an excluded relation, and with it any element it strands', () => {
    // GOL@1 keeps its realization from APP@1, so it stays; GOL@2's only relation was the
    // aggregation, so it goes. A scatter of unconnected boxes is what the filter is for removing.
    const result = narrowed(ARCHIMATE, { connection_type: ['archimate-aggregation'] }, NODES, EDGES)

    expect(result.nodes.map((n) => n.id)).toEqual(['GOL@1', 'APP@1'])
    expect(result.edges).toEqual([EDGES[1]])
  })

  it('keeps an element the caller says it cannot lose, however isolated', () => {
    // The element being explored: filtering out its relationships would otherwise empty the canvas
    // and leave nothing to explore from.
    const result = narrowed(
      ARCHIMATE,
      { connection_type: ['archimate-aggregation'] },
      NODES,
      EDGES,
      new Set(['GOL@2']),
    )

    expect(result.nodes.map((n) => n.id)).toContain('GOL@2')
  })

  it('keeps an element that never had a relation, because the filter took none from it', () => {
    // Otherwise "hide the unconnected" would hide it with no filter active at all, and an
    // unfiltered graph has to show everything it loaded.
    const lonely = node('VAL@1', 'motivation', 'value')

    const unfiltered = narrowed(ARCHIMATE, {}, [...NODES, lonely], EDGES)
    const filtered = narrowed(ARCHIMATE, { entity_type: ['goal'] }, [...NODES, lonely], EDGES)

    expect(unfiltered.nodes.map((n) => n.id)).toContain('VAL@1')
    expect(filtered.nodes.map((n) => n.id)).toContain('VAL@1')
  })

  it('strands nothing when every relation survives', () => {
    const result = narrowed(ARCHIMATE, { entity_type: ['outcome'] }, NODES, EDGES)

    expect(result.nodes).toHaveLength(3)
  })

  it('narrows an unfiltered graph to itself', () => {
    const result = narrowed(ARCHIMATE, {}, NODES, EDGES)

    expect(result.nodes).toEqual(NODES)
    expect(result.edges).toEqual(EDGES)
  })

  it('removes a whole subgraph the filter cut off from the anchor, not only lone elements', () => {
    // The case that matters on a walk: a cluster keeps its own relations and loses every path back
    // to the element being explored. Nothing about it is isolated — it is simply no longer an
    // answer to "what does this touch", and the radial layout would file it on a ring beyond the
    // farthest real one, drawing it as though it were one hop further out than the rest.
    const far = [node('FAR@1', 'business', 'business-process'), node('FAR@2', 'business', 'business-process')]
    const edges = [
      ...EDGES,
      edge('GOL@2', 'FAR@1', 'archimate-association'),   // the only path from the walk to them
      edge('FAR@1', 'FAR@2', 'archimate-realization'),   // and they hold each other
    ]

    const result = narrowed(
      ARCHIMATE, { connection_type: ['archimate-association'] }, [...NODES, ...far], edges,
      new Set(['GOL@1']),
    )

    expect(result.nodes.map((n) => n.id)).not.toContain('FAR@1')
    expect(result.nodes.map((n) => n.id)).not.toContain('FAR@2')
    // And the relation that held them to each other goes with them, rather than floating.
    expect(result.edges.some((e) => e.source === 'FAR@1' || e.target === 'FAR@1')).toBe(false)
  })

  it('keeps a cluster that still has a path back, however many hops it takes', () => {
    const far = [node('FAR@1', 'business', 'business-process'), node('FAR@2', 'business', 'business-process')]
    const edges = [
      ...EDGES,
      edge('GOL@2', 'FAR@1', 'archimate-realization'),
      edge('FAR@1', 'FAR@2', 'archimate-realization'),
    ]

    // GOL@1 → GOL@2 → FAR@1 → FAR@2: three hops, all surviving.
    const result = narrowed(
      ARCHIMATE, { connection_type: ['archimate-influence'] }, [...NODES, ...far], edges,
      new Set(['GOL@1']),
    )

    expect(result.nodes.map((n) => n.id)).toContain('FAR@2')
  })

  it('keeps a disconnected cluster where there is no anchor to be disconnected from', () => {
    // A viewpoint's result is a set rather than a neighbourhood, and the assurance explorer has an
    // unanchored route that opens on the whole visible graph. Reachability needs somewhere to start.
    const far = [node('FAR@1', 'business', 'business-process'), node('FAR@2', 'business', 'business-process')]
    const edges = [
      ...EDGES,
      edge('GOL@2', 'FAR@1', 'archimate-association'),
      edge('FAR@1', 'FAR@2', 'archimate-realization'),
    ]

    const result = narrowed(
      ARCHIMATE, { connection_type: ['archimate-association'] }, [...NODES, ...far], edges,
    )

    expect(result.nodes.map((n) => n.id)).toContain('FAR@1')
  })

  it('narrows the same graph the same way under the other meta-ontology', () => {
    // The selection is keyed on *that* chain's level ids, and nothing in the module had to change.
    const result = narrowed(OTHER, { tier: ['application'] }, NODES, EDGES)

    expect(result.nodes.map((n) => n.id)).toEqual(['GOL@1', 'GOL@2'])
    expect(result.edges).toEqual([EDGES[0]])
  })

  it('ignores a selection naming a level the meta-ontology in play does not declare', () => {
    // ArchiMate's own level id, against the other chain: it must not silently hide anything.
    const result = narrowed(OTHER, { domain: ['motivation'] }, NODES, EDGES)

    expect(result.nodes).toEqual(NODES)
  })
})

describe('the levels are data, never a type', () => {
  it('accepts a level id this codebase has never seen', () => {
    const invented: ClassificationLevel = {
      id: 'какой-то-уровень',
      label: 'Some level',
      source: 'hierarchy',
      required: false,
    }

    expect(facetOptions([invented], NODES)).toEqual([
      { level: invented, values: ['application', 'motivation'] },
    ])
  })
})
