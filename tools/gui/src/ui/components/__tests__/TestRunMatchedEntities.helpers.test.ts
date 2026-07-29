import { describe, expect, it } from 'vitest'
import {
  MATCHED_DISPLAY_CAP, cappedMatches, derivedMatchTag, hiddenMatchCount,
} from '../TestRunMatchedEntities.helpers'
import type { EntityItemSummary } from '../../../domain'

const entity = (overrides: Partial<EntityItemSummary> = {}): EntityItemSummary => ({
  id: 'APC@1.EntSch.a', name: 'Alpha', type: 'application-component',
  specialization_slugs: [], group: 'uncategorized', membership: 'primary', domain: 'application',
  status: 'draft', version: '1', column_values: null, anchor_modeled_distance: null, matched_via_derived_hops: null, ...overrides,
})

describe('derivedMatchTag', () => {
  it('tags an entity whose match rested on derived evidence with the witness length', () => {
    expect(derivedMatchTag(entity({ matched_via_derived_hops: 2 }))).toBe('matched via derived (2 hops)')
  })

  it('gives no tag when the match holds on modeled facts alone', () => {
    expect(derivedMatchTag(entity())).toBeNull()
  })
})

describe('cappedMatches / hiddenMatchCount', () => {
  const many = Array.from({ length: MATCHED_DISPLAY_CAP + 10 }, (_, i) => entity({ id: `e${i}` }))

  it('caps the display list', () => {
    expect(cappedMatches(many)).toHaveLength(MATCHED_DISPLAY_CAP)
  })

  it('reports the remainder against the execution total, not the returned page', () => {
    expect(hiddenMatchCount(many, 200)).toBe(200 - MATCHED_DISPLAY_CAP)
    expect(hiddenMatchCount(many.slice(0, 3), 3)).toBe(0)
  })
})
