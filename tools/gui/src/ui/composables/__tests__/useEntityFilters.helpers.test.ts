/**
 * Tests for the pure helper functions exported from useEntityFilters.ts:
 * buildTypeToDomain, deriveImpliedDomains, intersectWithFixed.
 *
 * Tests run without Vue setup context (no composable mounting needed).
 */
import { describe, it, expect } from 'vitest'
import {
  buildTypeToDomain,
  deriveImpliedDomains,
  intersectWithFixed,
} from '../useEntityFilters'

const DOMAIN_MAP = {
  application: ['application-component', 'application-service', 'application-interface'],
  business: ['business-process', 'business-function', 'business-role'],
  technology: ['node', 'system-software', 'technology-service'],
}

describe('buildTypeToDomain', () => {
  it('inverts the domain→types map to type→domain', () => {
    const result = buildTypeToDomain(DOMAIN_MAP)
    expect(result['application-component']).toBe('application')
    expect(result['business-process']).toBe('business')
    expect(result['node']).toBe('technology')
  })

  it('returns an empty object for an empty input', () => {
    expect(buildTypeToDomain({})).toEqual({})
  })

  it('all types from all domains are present', () => {
    const result = buildTypeToDomain(DOMAIN_MAP)
    const allTypes = Object.values(DOMAIN_MAP).flat()
    for (const t of allTypes) {
      expect(result).toHaveProperty(t)
    }
  })
})

describe('deriveImpliedDomains', () => {
  const typeToDomain = buildTypeToDomain(DOMAIN_MAP)

  it('returns implied domain for a single selected type', () => {
    const result = deriveImpliedDomains(['application-component'], typeToDomain)
    expect(result).toEqual(['application'])
  })

  it('returns multiple distinct domains for types from different domains', () => {
    const result = deriveImpliedDomains(['application-component', 'business-role'], typeToDomain)
    expect(result).toContain('application')
    expect(result).toContain('business')
    expect(result).toHaveLength(2)
  })

  it('deduplicates domains when multiple types share a domain', () => {
    const result = deriveImpliedDomains(
      ['application-component', 'application-service'],
      typeToDomain,
    )
    expect(result).toEqual(['application'])
  })

  it('returns empty array when no types are selected', () => {
    expect(deriveImpliedDomains([], typeToDomain)).toEqual([])
  })

  it('ignores unknown types (not in map)', () => {
    const result = deriveImpliedDomains(['unknown-type', 'application-component'], typeToDomain)
    expect(result).toEqual(['application'])
  })
})

describe('intersectWithFixed', () => {
  const allTypes = ['application-component', 'application-service', 'business-process', 'node']

  it('returns all available when no fixedEntityTypes provided', () => {
    expect(intersectWithFixed(allTypes)).toEqual(allTypes)
    expect(intersectWithFixed(allTypes, [])).toEqual(allTypes)
    expect(intersectWithFixed(allTypes, undefined)).toEqual(allTypes)
  })

  it('filters to intersection with fixedEntityTypes', () => {
    const result = intersectWithFixed(allTypes, ['application-component', 'node'])
    expect(result).toEqual(['application-component', 'node'])
  })

  it('returns empty array when intersection is empty', () => {
    const result = intersectWithFixed(allTypes, ['unknown-type'])
    expect(result).toEqual([])
  })

  it('preserves order from available array', () => {
    const available = ['node', 'application-component', 'business-process']
    const result = intersectWithFixed(available, ['business-process', 'node'])
    expect(result).toEqual(['node', 'business-process'])
  })
})
