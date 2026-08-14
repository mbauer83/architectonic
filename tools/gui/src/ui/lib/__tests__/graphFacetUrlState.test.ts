import { describe, expect, it } from 'vitest'
import type { LocationQuery } from 'vue-router'
import {
  decodeFacetSelection,
  encodeFacetSelection,
  facetSelectionNeedsNormalization,
  withFacetSelection,
  withValueToggled,
} from '../graphFacetUrlState'

describe('a filtered graph is a link', () => {
  it('round-trips a selection through the query', () => {
    const selection = { domain: ['motivation'], entity_type: ['goal', 'outcome'] }

    const query = withFacetSelection({}, selection) as LocationQuery
    expect(decodeFacetSelection(query)).toEqual({
      domain: ['motivation'],
      entity_type: ['goal', 'outcome'],
    })
  })

  it('says nothing when nothing is excluded, as All is the absence of the key', () => {
    expect(encodeFacetSelection({})).toBeUndefined()
    expect(withFacetSelection({ viewpoint: 'v1' }, {})).toEqual({ viewpoint: 'v1' })
  })

  it('preserves the query keys the graph explorer already carries', () => {
    const query = { viewpoint: 'v1', 'param.gaps_only': 'maybe' }

    expect(withFacetSelection(query, { domain: ['motivation'] })).toEqual({
      viewpoint: 'v1',
      'param.gaps_only': 'maybe',
      hide: 'domain:motivation',
    })
  })

  it('encodes in a stable order, so the same selection is the same link', () => {
    const one = encodeFacetSelection({ entity_type: ['outcome', 'goal'], domain: ['motivation'] })
    const other = encodeFacetSelection({ domain: ['motivation'], entity_type: ['goal', 'outcome'] })

    expect(one).toBe(other)
  })
})

describe('what a hand-edited link may contain', () => {
  it.each([
    ['', {}],
    ['nonsense', {}],
    [':novalue', {}],
    ['domain:', {}],
    ['domain:motivation,', { domain: ['motivation'] }],
  ])('decodes %o without throwing', (raw, expected) => {
    expect(decodeFacetSelection({ hide: raw })).toEqual(expected)
  })

  it('keeps a colon inside a value, which is not this module to constrain', () => {
    expect(decodeFacetSelection({ hide: 'specialization:ns:core' })).toEqual({
      specialization: ['ns:core'],
    })
  })

  it('accepts a level id from a meta-ontology this codebase has never seen', () => {
    expect(decodeFacetSelection({ hide: 'tier:application' })).toEqual({ tier: ['application'] })
  })

  it('reports a non-canonical key so the surface can normalize it once', () => {
    expect(facetSelectionNeedsNormalization({})).toBe(false)
    expect(facetSelectionNeedsNormalization({ hide: 'domain:motivation' })).toBe(false)
    expect(facetSelectionNeedsNormalization({ hide: 'garbage' })).toBe(true)
    expect(facetSelectionNeedsNormalization({ hide: ['a', 'b'] })).toBe(true)
  })
})

describe('toggling one value', () => {
  it('adds a value not yet excluded', () => {
    expect(withValueToggled({}, 'domain', 'motivation')).toEqual({ domain: ['motivation'] })
  })

  it('removes a value already excluded', () => {
    expect(withValueToggled({ domain: ['motivation'] }, 'domain', 'motivation')).toEqual({})
  })

  it('drops the level entirely when its last value is removed, so the link stays canonical', () => {
    const selection = withValueToggled({ domain: ['motivation'], entity_type: ['goal'] }, 'domain', 'motivation')

    expect(selection).toEqual({ entity_type: ['goal'] })
    expect(Object.keys(selection)).not.toContain('domain')
  })

  it('leaves other levels alone', () => {
    expect(withValueToggled({ entity_type: ['goal'] }, 'domain', 'motivation')).toEqual({
      entity_type: ['goal'],
      domain: ['motivation'],
    })
  })
})
