import { describe, it, expect } from 'vitest'
import {
  diagramListParams,
  documentListParams,
  entityListScope,
  savedGroupToMerge,
  tierFromViewpointFilter,
  viewpointFilterFromTier,
} from '../listRequestParams'

describe('documents facet → fetch mapping', () => {
  it.each([
    ['all', '', {}],
    ['engagement', '', { scope: 'engagement' }],
    ['enterprise', '', { scope: 'global' }],
    ['enterprise', 'adr', { doc_type: 'adr', scope: 'global' }],
    ['all', 'standard', { doc_type: 'standard' }],
  ] as const)('tier=%s doc_type=%s', (tier, docType, expected) => {
    expect(documentListParams(tier, docType)).toEqual(expected)
  })
})

describe('diagrams facet → fetch mapping', () => {
  it('All sends no scope; tiers map to the API vocabulary', () => {
    expect(diagramListParams('all')).toEqual({})
    expect(diagramListParams('engagement')).toEqual({ scope: 'engagement' })
    expect(diagramListParams('enterprise')).toEqual({ scope: 'global' })
  })
})

describe('entities facet → fetch mapping', () => {
  it('group view forces engagement scope regardless of tier', () => {
    expect(entityListScope('all', true)).toBe('engagement')
    expect(entityListScope('engagement', true)).toBe('engagement')
  })

  it('non-group view follows the tier facet', () => {
    expect(entityListScope('all', false)).toBeUndefined()
    expect(entityListScope('engagement', false)).toBe('engagement')
    expect(entityListScope('enterprise', false)).toBe('global')
  })
})

describe('saved collection preference', () => {
  it('clean localStorage never merges — the list loads directly, no redirect', () => {
    expect(savedGroupToMerge('', 'all', null)).toBeNull()
    expect(savedGroupToMerge('', 'engagement', null)).toBeNull()
  })

  it('merges only when no group is selected and the tier allows collections', () => {
    expect(savedGroupToMerge('', 'all', 'my-project')).toBe('my-project')
    expect(savedGroupToMerge('', 'engagement', 'my-project')).toBe('my-project')
    expect(savedGroupToMerge('active', 'all', 'my-project')).toBeNull()
    expect(savedGroupToMerge('', 'enterprise', 'my-project')).toBeNull()
  })

  it('an empty saved preference means All — nothing to restore', () => {
    expect(savedGroupToMerge('', 'all', '')).toBeNull()
  })
})

describe('viewpoint catalog filter ↔ tier facet', () => {
  it('round-trips every selection, with "" meaning All', () => {
    expect(viewpointFilterFromTier('all')).toBe('')
    expect(viewpointFilterFromTier('module')).toBe('module')
    expect(tierFromViewpointFilter('')).toBe('all')
    expect(tierFromViewpointFilter('enterprise')).toBe('enterprise')
  })
})
