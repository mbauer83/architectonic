import { describe, expect, it } from 'vitest'
import { definitionFromMapping, definitionToMapping } from './viewpointDefinitionSerialization'
import { isEmptyQuery, queryFromScopeDraft } from './viewpointDefinitionDraft'
import { mkQuery } from './viewpointCriteria'

// Same five representative definitions exercised by the Python fixture suite — one canonical
// mapping shared by both the Python and TypeScript parsers/serializers.
const CANONICAL_EXAMPLES: Record<string, unknown>[] = [
  {
    slug: 'application-components', version: 1, name: 'Application Components',
    purpose: 'informing', content: 'overview',
    query: {
      query_schema: 1,
      entity_criteria: {
        kind: 'group', conjunction: 'and',
        children: [{ kind: 'condition', attribute: 'type', comparator: 'in', value: ['application-component'] }],
      },
    },
  },
  {
    slug: 'active-app-tech', version: 1, name: 'Active Application & Technology',
    query: {
      query_schema: 1,
      entity_criteria: {
        kind: 'group', conjunction: 'and',
        children: [
          {
            kind: 'group', conjunction: 'or',
            children: [
              { kind: 'condition', attribute: 'domain', comparator: 'eq', value: 'application' },
              { kind: 'condition', attribute: 'domain', comparator: 'eq', value: 'technology' },
            ],
          },
          { kind: 'condition', attribute: 'status', comparator: 'eq', value: 'deprecated', negate: true },
        ],
      },
    },
  },
  {
    slug: 'components-serving-processes', version: 2, name: 'Components Serving Processes',
    query: {
      query_schema: 1,
      entity_criteria: {
        kind: 'group', conjunction: 'and',
        children: [
          { kind: 'condition', attribute: 'type', comparator: 'eq', value: 'application-component' },
          {
            kind: 'incident', direction: 'outgoing',
            connection_criteria: {
              kind: 'group', conjunction: 'and',
              children: [
                { kind: 'condition', attribute: 'type', comparator: 'eq', value: 'archimate-serving' },
                { kind: 'condition', attribute: 'strength', comparator: 'gte', value: 3 },
              ],
            },
            endpoint_criteria: {
              kind: 'group', conjunction: 'and',
              children: [
                { kind: 'condition', attribute: 'type', comparator: 'eq', value: 'process' },
                { kind: 'condition', attribute: 'specialization', comparator: 'eq', value: 'business-process' },
              ],
            },
          },
        ],
      },
      include_connected: [
        {
          direction: 'outgoing',
          connection_criteria: {
            kind: 'group', conjunction: 'and',
            children: [{ kind: 'condition', attribute: 'type', comparator: 'eq', value: 'archimate-serving' }],
          },
          neighbor_criteria: {
            kind: 'group', conjunction: 'and',
            children: [
              { kind: 'condition', attribute: 'type', comparator: 'eq', value: 'process' },
              { kind: 'condition', attribute: 'specialization', comparator: 'eq', value: 'business-process' },
            ],
          },
        },
      ],
      connections: {
        enabled: true,
        criteria: {
          kind: 'group', conjunction: 'and',
          children: [
            { kind: 'condition', attribute: 'type', comparator: 'eq', value: 'archimate-serving' },
            { kind: 'condition', attribute: 'strength', comparator: 'gte', value: { from: 'target', attribute: 'threshold' } },
          ],
        },
      },
    },
  },
  {
    slug: 'component-lifecycle-table', version: 1, name: 'Component Lifecycle',
    query: {
      query_schema: 1,
      entity_criteria: {
        kind: 'group', conjunction: 'and',
        children: [{ kind: 'condition', attribute: 'type', comparator: 'eq', value: 'application-component' }],
      },
    },
    presentation: {
      representation: 'table',
      columns: [
        { label: 'Name', source: 'name' },
        { label: 'Status', source: 'status' },
        { label: 'Risk', source: 'risk_score' },
      ],
      styling_rules: [
        {
          capability: 'badges', mode: 'match',
          match_criteria: {
            kind: 'group', conjunction: 'and',
            children: [{ kind: 'condition', attribute: 'status', comparator: 'eq', value: 'deprecated' }],
          },
          value: 'badge-warning',
        },
        {
          capability: 'badges', mode: 'range', range_attribute: 'risk_score',
          range_bands: [
            { minimum: null, maximum: 4, value: 'badge-ok' },
            { minimum: 4, maximum: 7, value: 'badge-caution' },
            { minimum: 7, maximum: null, value: 'badge-danger' },
          ],
        },
      ],
      default_style: { badges: 'badge-neutral' },
    },
  },
  {
    slug: 'impact-heatmap', version: 1, name: 'Impact Heatmap',
    query: {
      query_schema: 1,
      entity_criteria: { kind: 'group', conjunction: 'and', children: [] },
    },
    presentation: {
      representation: 'exploration',
      display_options: { layout: 'radial' },
      styling_rules: [
        {
          capability: 'node_color', mode: 'scale',
          scale_attribute: 'derived.impact-distance', scale_min: 0, scale_max: 6,
          scale_tokens: ['heat-near', '#123456'],
        },
      ],
      default_style: { node_color: '#a1b2c3' },
    },
  },
  {
    slug: 'requirement-coverage', version: 1, name: 'Requirement Coverage',
    query: {
      query_schema: 1,
      entity_criteria: { kind: 'group', conjunction: 'and', children: [] },
      connections: {
        enabled: true,
        criteria: {
          kind: 'group', conjunction: 'and',
          children: [{ kind: 'condition', attribute: 'type', comparator: 'eq', value: 'archimate-realization' }],
        },
      },
    },
    presentation: {
      representation: 'matrix',
      row_criteria: {
        kind: 'group', conjunction: 'and',
        children: [{ kind: 'condition', attribute: 'type', comparator: 'eq', value: 'requirement' }],
      },
      column_criteria: {
        kind: 'group', conjunction: 'and',
        children: [{ kind: 'condition', attribute: 'type', comparator: 'eq', value: 'application-component' }],
      },
    },
  },
]

describe('canonical example round-trip', () => {
  // Mirrors the Python fixture suite's own property: `parse` fills
  // in defaults the fixture omits (e.g. `purpose`/`content`, `connections.enabled: true`) and
  // `serialize` omits-on-write anything equal to a default, so the fixture's raw mapping and
  // its serialization legitimately differ. What must hold — and is id-noise-free, since a
  // builder node's `id` is UI-only and never survives serialization — is
  // `serialize(parse(serialize(parse(x)))) == serialize(parse(x))`: once through the wire
  // mapping and back is lossless.
  it.each(CANONICAL_EXAMPLES.map((example) => [example.slug as string, example] as const))(
    'wire mapping is stable across a second parse/serialize round-trip for %s',
    (_slug, example) => {
      const mapping = definitionToMapping(definitionFromMapping(example))
      const reMapping = definitionToMapping(definitionFromMapping(mapping))
      expect(reMapping).toEqual(mapping)
    },
  )
})

describe('selection mode', () => {
  it('every GUI save states its selection mode explicitly', () => {
    const draft = definitionFromMapping({ slug: 'x', version: 1, name: 'X' })
    expect(definitionToMapping(draft).selection_mode).toBe('scope')
  })

  it('legacy definitions infer the engine legacy behavior: query when present, else scope', () => {
    const withQuery = definitionFromMapping(CANONICAL_EXAMPLES[0])
    expect(withQuery.selectionMode).toBe('query')
    const scopeOnly = definitionFromMapping({ slug: 'x', version: 1, name: 'X', scope: { entity_types: ['goal'] } })
    expect(scopeOnly.selectionMode).toBe('scope')
  })

  it('round-trips a stamped mode', () => {
    const draft = definitionFromMapping({ slug: 'x', version: 1, name: 'X', selection_mode: 'scope' })
    expect(draft.selectionMode).toBe('scope')
    expect(definitionToMapping(draft).selection_mode).toBe('scope')
  })

  it('drops a pristine builder query in scope mode instead of persisting a divergent layer', () => {
    const draft = definitionFromMapping({ slug: 'x', version: 1, name: 'X', scope: { entity_types: ['goal'] } })
    // A fresh editor session materializes an empty builder query; scope mode must not persist it.
    draft.query = mkQuery()
    expect(definitionToMapping(draft).query).toBeUndefined()
  })

  it('keeps a NON-empty query as inactive history in scope mode', () => {
    const draft = definitionFromMapping(CANONICAL_EXAMPLES[0])
    draft.selectionMode = 'scope'
    const mapping = definitionToMapping(draft)
    expect(mapping.selection_mode).toBe('scope')
    expect(mapping.query).toBeDefined()
  })
})

describe('queryFromScopeDraft conversion', () => {
  it('translates the scope entity types to an explicit type-in condition', () => {
    const query = queryFromScopeDraft({
      entityTypes: ['process', 'goal'], connectionTypes: null,
      excludedEntityTypes: [], excludedDomains: [], excludedConnectionTypes: [],
    })
    const [condition] = query.entityCriteria.children
    expect(condition).toMatchObject({
      kind: 'condition', attribute: 'type', comparator: 'in',
      value: { kind: 'literal', literal: ['goal', 'process'] },
    })
  })

  it('yields a match-all query for an unrestricted scope', () => {
    const query = queryFromScopeDraft({
      entityTypes: null, connectionTypes: null,
      excludedEntityTypes: [], excludedDomains: [], excludedConnectionTypes: [],
    })
    expect(isEmptyQuery(query)).toBe(true)
  })
})

describe('scale rule and layout wire keys', () => {
  const example = CANONICAL_EXAMPLES.find((candidate) => candidate.slug === 'impact-heatmap')

  it('round-trips scale_attribute/scale_min/scale_max/scale_tokens exactly', () => {
    const mapping = definitionToMapping(definitionFromMapping(example as Record<string, unknown>))
    const presentation = mapping.presentation as Record<string, unknown>
    expect(presentation.styling_rules).toEqual([
      {
        capability: 'node_color', mode: 'scale',
        scale_attribute: 'derived.impact-distance', scale_min: 0, scale_max: 6,
        scale_tokens: ['heat-near', '#123456'],
      },
    ])
    expect(presentation.default_style).toEqual({ node_color: '#a1b2c3' })
  })

  it('round-trips display_options.layout', () => {
    const mapping = definitionToMapping(definitionFromMapping(example as Record<string, unknown>))
    const presentation = mapping.presentation as Record<string, unknown>
    expect(presentation.display_options).toEqual({ layout: 'radial' })
  })
})
