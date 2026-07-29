import { describe, expect, it } from 'vitest'
import { buildEphemeralRequest } from './ephemeralViewpointRequest'
import { mkQuery } from '../../domain/viewpointCriteria'
import { mkPresentation } from '../../domain/viewpointPresentation'
import type { CriteriaCatalog } from '../../domain'

// buildEphemeralRequest only consults the catalog's attribute-type tables.
const emptyCatalog = { entity_attribute_types: {}, connection_attribute_types: {} } as CriteriaCatalog

describe('buildEphemeralRequest', () => {
  it('composition mode carries the inline query + presentation, with no slug', () => {
    const request = buildEphemeralRequest(mkQuery(), mkPresentation('table'), emptyCatalog, null)
    expect(request.query).toBeDefined()
    expect(request.slug).toBeUndefined()
    expect(request.presentation).toBeDefined()
    expect(request.parameters).toEqual({})
  })

  it('override mode carries { slug, presentation } and NO query — the saved definition drives the population', () => {
    const request = buildEphemeralRequest(mkQuery(), mkPresentation('matrix'), emptyCatalog, 'capability-map')
    expect(request.slug).toBe('capability-map')
    expect(request.query).toBeUndefined()
    expect(request.presentation).toBeDefined()
    expect(request.parameters).toEqual({})
  })

  it('always issues the effective presentation, so a styled result matches the editor', () => {
    const styled = buildEphemeralRequest(mkQuery(), mkPresentation('diagram'), emptyCatalog, null)
    expect(styled.presentation).toBeDefined()
  })

  it('omits presentation when none is set (a bare match-all run)', () => {
    const bare = buildEphemeralRequest(mkQuery(), null, emptyCatalog, null)
    expect(bare.presentation).toBeUndefined()
    expect(bare.query).toBeDefined()
  })

  it('threads resolved runtime parameters into the request in composition mode', () => {
    const request = buildEphemeralRequest(mkQuery(), null, emptyCatalog, null, { minLevel: 3, tag: 'core' })
    expect(request.parameters).toEqual({ minLevel: 3, tag: 'core' })
  })

  it('threads resolved runtime parameters into a saved-slug override too', () => {
    const request = buildEphemeralRequest(mkQuery(), null, emptyCatalog, 'capability-map', { minLevel: 3 })
    expect(request.slug).toBe('capability-map')
    expect(request.parameters).toEqual({ minLevel: 3 })
  })

  it('defaults parameters to empty when the caller supplies none (query declares none)', () => {
    const request = buildEphemeralRequest(mkQuery(), null, emptyCatalog, null)
    expect(request.parameters).toEqual({})
  })
})
