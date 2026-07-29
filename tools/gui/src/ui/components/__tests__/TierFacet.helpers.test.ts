import { describe, it, expect } from 'vitest'
import { LIST_TIERS, VIEWPOINT_TIERS } from '../../lib/tierUrlState'
import { tierFacetOptions } from '../TierFacet.helpers'

describe('tierFacetOptions', () => {
  it('list surfaces offer All, Engagement, Enterprise', () => {
    expect(tierFacetOptions(LIST_TIERS)).toEqual([
      { value: 'all', label: 'All' },
      { value: 'engagement', label: 'Engagement' },
      { value: 'enterprise', label: 'Enterprise' },
    ])
  })

  it('viewpoints additionally offer the module tier', () => {
    expect(tierFacetOptions(VIEWPOINT_TIERS).map((option) => option.value)).toEqual([
      'all',
      'engagement',
      'enterprise',
      'module',
    ])
  })

  it('never renders Global as a label', () => {
    for (const option of tierFacetOptions(VIEWPOINT_TIERS)) {
      expect(option.label).not.toMatch(/global/i)
    }
  })
})
