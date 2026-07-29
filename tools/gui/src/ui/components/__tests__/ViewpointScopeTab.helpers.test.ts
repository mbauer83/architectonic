import { describe, expect, it } from 'vitest'
import {
  carveOutFromDomainExclusion,
  connectionScopeMode,
  entityExclusionState,
  entityScopeMode,
  excludeDomain,
  excludeDomainFromIncludeList,
  filterByQuery,
  groupByDomain,
  includeDomain,
  reincludeDomain,
  toggleInList,
  withConnectionScopeMode,
  withEntityScopeMode,
} from '../ViewpointScopeTab.helpers'
import { mkScope } from '../../../domain/viewpointDefinitionDraft'

const DOMAINS: Record<string, string> = {
  'application-component': 'application',
  'application-service': 'application',
  process: 'common',
}

describe('groupByDomain', () => {
  it('groups and sorts types by domain, sorting types within each domain', () => {
    expect(groupByDomain(['process', 'application-service', 'application-component'], DOMAINS)).toEqual([
      { domain: 'application', types: ['application-component', 'application-service'] },
      { domain: 'common', types: ['process'] },
    ])
  })

  it('buckets a type with no known domain under (unknown)', () => {
    expect(groupByDomain(['mystery-type'], DOMAINS)).toEqual([{ domain: '(unknown)', types: ['mystery-type'] }])
  })
})

describe('entityScopeMode / connectionScopeMode', () => {
  it('is unrestricted when no include list and no exclusions are set', () => {
    expect(entityScopeMode(mkScope())).toBe('unrestricted')
    expect(connectionScopeMode(mkScope())).toBe('unrestricted')
  })

  it('is include when the allow-list is non-null, regardless of exclusions', () => {
    expect(entityScopeMode({ ...mkScope(), entityTypes: [] })).toBe('include')
    expect(connectionScopeMode({ ...mkScope(), connectionTypes: ['archimate-serving'] })).toBe('include')
  })

  it('is exclude when the allow-list is null but an exclusion field is populated', () => {
    expect(entityScopeMode({ ...mkScope(), excludedEntityTypes: ['process'] })).toBe('exclude')
    expect(entityScopeMode({ ...mkScope(), excludedDomains: ['application'] })).toBe('exclude')
    expect(connectionScopeMode({ ...mkScope(), excludedConnectionTypes: ['archimate-serving'] })).toBe('exclude')
  })
})

describe('withEntityScopeMode / withConnectionScopeMode', () => {
  it('switching to unrestricted clears the allow-list and both exclusion fields', () => {
    const scope = { ...mkScope(), entityTypes: ['a'], excludedEntityTypes: ['b'], excludedDomains: ['d'] }
    expect(withEntityScopeMode(scope, 'unrestricted')).toEqual({
      ...scope, entityTypes: null, excludedEntityTypes: [], excludedDomains: [],
    })
  })

  it('switching to include seeds an empty allow-list and clears exclusions', () => {
    const scope = { ...mkScope(), excludedEntityTypes: ['b'], excludedDomains: ['d'] }
    expect(withEntityScopeMode(scope, 'include')).toEqual({ ...scope, entityTypes: [], excludedEntityTypes: [], excludedDomains: [] })
  })

  it('switching to include preserves an existing allow-list', () => {
    const scope = { ...mkScope(), entityTypes: ['a', 'b'] }
    expect(withEntityScopeMode(scope, 'include').entityTypes).toEqual(['a', 'b'])
  })

  it('switching to exclude nulls the allow-list, leaving exclusion fields untouched', () => {
    const scope = { ...mkScope(), entityTypes: ['a'] }
    expect(withEntityScopeMode(scope, 'exclude')).toEqual({ ...scope, entityTypes: null })
  })

  it('mirrors the same transitions for connection scope mode', () => {
    const scope = { ...mkScope(), connectionTypes: ['a'], excludedConnectionTypes: ['b'] }
    expect(withConnectionScopeMode(scope, 'unrestricted')).toEqual({ ...scope, connectionTypes: null, excludedConnectionTypes: [] })
    expect(withConnectionScopeMode(mkScope(), 'include').connectionTypes).toEqual([])
  })
})

describe('toggleInList', () => {
  it('adds an absent value and removes a present one', () => {
    expect(toggleInList(['a'], 'b')).toEqual(['a', 'b'])
    expect(toggleInList(['a', 'b'], 'a')).toEqual(['b'])
  })
})

describe('entityExclusionState', () => {
  it('is inherited when the domain is bulk-excluded, even if also individually listed', () => {
    expect(entityExclusionState('a', 'application', ['application'], ['a'])).toBe('inherited')
  })

  it('is explicit when only individually excluded', () => {
    expect(entityExclusionState('a', 'application', [], ['a'])).toBe('explicit')
  })

  it('is none otherwise', () => {
    expect(entityExclusionState('a', 'application', [], [])).toBe('none')
  })
})

describe('excludeDomain / reincludeDomain', () => {
  it('adds the domain and drops now-redundant per-type entries it covers', () => {
    const scope = { ...mkScope(), excludedEntityTypes: ['application-component', 'process'] }
    const result = excludeDomain(scope, 'application', ['application-component', 'application-service'])
    expect(result.excludedDomains).toEqual(['application'])
    expect(result.excludedEntityTypes).toEqual(['process'])
  })

  it('is idempotent when the domain is already excluded', () => {
    const scope = { ...mkScope(), excludedDomains: ['application'] }
    expect(excludeDomain(scope, 'application', []).excludedDomains).toEqual(['application'])
  })

  it('reincludeDomain removes the domain from the exclusion list', () => {
    const scope = { ...mkScope(), excludedDomains: ['application', 'common'] }
    expect(reincludeDomain(scope, 'application').excludedDomains).toEqual(['common'])
  })
})

describe('carveOutFromDomainExclusion', () => {
  it('replaces the domain exclusion with explicit exclusions for every sibling', () => {
    const scope = { ...mkScope(), excludedDomains: ['application'] }
    const result = carveOutFromDomainExclusion(
      scope, 'application-service', 'application', ['application-component', 'application-service'],
    )
    expect(result.excludedDomains).toEqual([])
    expect(result.excludedEntityTypes).toEqual(['application-component'])
  })

  it('merges siblings into any pre-existing explicit exclusions without duplicating', () => {
    const scope = { ...mkScope(), excludedDomains: ['application'], excludedEntityTypes: ['application-component'] }
    const result = carveOutFromDomainExclusion(
      scope, 'application-service', 'application', ['application-component', 'application-service'],
    )
    expect(result.excludedEntityTypes).toEqual(['application-component'])
  })
})

describe('includeDomain / excludeDomainFromIncludeList', () => {
  it('includeDomain unions the domain members into the allow-list without duplicating', () => {
    const scope = { ...mkScope(), entityTypes: ['application-component'] }
    expect(includeDomain(scope, ['application-component', 'application-service']).entityTypes)
      .toEqual(['application-component', 'application-service'])
  })

  it('excludeDomainFromIncludeList removes every member of the domain from the allow-list', () => {
    const scope = { ...mkScope(), entityTypes: ['application-component', 'application-service', 'process'] }
    expect(excludeDomainFromIncludeList(scope, ['application-component', 'application-service']).entityTypes).toEqual(['process'])
  })
})

describe('filterByQuery', () => {
  it('is case-insensitive and matches substrings', () => {
    expect(filterByQuery(['application-component', 'process'], 'APP')).toEqual(['application-component'])
  })

  it('returns everything for a blank query', () => {
    expect(filterByQuery(['a', 'b'], '  ')).toEqual(['a', 'b'])
  })

  it('returns nothing when nothing matches', () => {
    expect(filterByQuery(['application-component'], 'zzz')).toEqual([])
  })
})
