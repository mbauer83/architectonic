import { describe, it, expect } from 'vitest'
import {
  ALL_GROUPS,
  diagramListParams,
  documentListParams,
  entityListScope,
  groupFromQuery,
  repositoryWideDomainQuery,
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

describe('the ?group= value resolves to a collection', () => {
  it('an absent parameter and the all-collections value both mean every collection', () => {
    expect(groupFromQuery(undefined)).toBe('')
    expect(groupFromQuery(ALL_GROUPS)).toBe('')
  })

  it('any other value is the collection itself', () => {
    expect(groupFromQuery('my-project')).toBe('my-project')
    expect(groupFromQuery('uncategorized')).toBe('uncategorized')
  })
})

describe('a repository-wide domain link', () => {
  it('names the scope its count was computed in, rather than leaving it absent', () => {
    expect(repositoryWideDomainQuery('motivation')).toEqual({
      domain: 'motivation',
      group: ALL_GROUPS,
    })
  })

  it('survives the saved-preference merge, which `{ domain }` alone does not', () => {
    // The regression, as a pair. The link the Home page used to build is the first line; the one it
    // builds now is the second. Only the second still means "every collection" on arrival.
    expect(savedGroupToMerge(undefined, 'all', 'my-project')).toBe('my-project')
    expect(
      savedGroupToMerge(repositoryWideDomainQuery('motivation').group, 'all', 'my-project'),
    ).toBeNull()
  })
})

describe('saved collection preference', () => {
  it('clean localStorage never merges — the list loads directly, no redirect', () => {
    expect(savedGroupToMerge(undefined, 'all', null)).toBeNull()
    expect(savedGroupToMerge(undefined, 'engagement', null)).toBeNull()
  })

  it('merges only when the caller expressed no scope and the tier allows collections', () => {
    expect(savedGroupToMerge(undefined, 'all', 'my-project')).toBe('my-project')
    expect(savedGroupToMerge(undefined, 'engagement', 'my-project')).toBe('my-project')
    expect(savedGroupToMerge('active', 'all', 'my-project')).toBeNull()
    expect(savedGroupToMerge(undefined, 'enterprise', 'my-project')).toBeNull()
  })

  it('an empty saved preference means All — nothing to restore', () => {
    expect(savedGroupToMerge(undefined, 'all', '')).toBeNull()
  })

  it('an explicit all-collections link is a decision, so the preference does not override it', () => {
    // The Home page's domain cards report `/api/stats`, which is repository-wide. Carrying no `group`
    // left them arriving inside whatever collection was last browsed: the card said 12 Motivation
    // entities and the destination showed the two that collection happened to hold. Both values below
    // resolve to "every collection" — the distinction is whether the caller *chose* it.
    expect(savedGroupToMerge(ALL_GROUPS, 'all', 'my-project')).toBeNull()
    expect(savedGroupToMerge(ALL_GROUPS, 'engagement', 'my-project')).toBeNull()
    expect(groupFromQuery(ALL_GROUPS)).toBe(groupFromQuery(undefined))
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
