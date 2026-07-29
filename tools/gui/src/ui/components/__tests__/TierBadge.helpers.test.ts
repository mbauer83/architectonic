import { describe, it, expect } from 'vitest'
import { TIER_LABELS, tierBadgeAriaLabel, tierDisplayLowercase, tierFromIsGlobal } from '../TierBadge.helpers'

describe('TIER_LABELS', () => {
  it('renders Enterprise, never Global', () => {
    expect(TIER_LABELS.enterprise).toBe('Enterprise')
    expect(Object.values(TIER_LABELS).join(' ')).not.toMatch(/global/i)
  })

  it('the module tier displays as Built-in (lowercase built-in inline)', () => {
    expect(TIER_LABELS.module).toBe('Built-in')
    expect(tierDisplayLowercase('module')).toBe('built-in')
    expect(tierDisplayLowercase('engagement')).toBe('engagement')
  })
})

describe('tierBadgeAriaLabel', () => {
  it('is the one semantic accessibility label per tier', () => {
    expect(tierBadgeAriaLabel('enterprise')).toBe('Repository tier: Enterprise')
    expect(tierBadgeAriaLabel('engagement')).toBe('Repository tier: Engagement')
  })
})

describe('tierFromIsGlobal', () => {
  it('maps the required list-contract flag to a tier', () => {
    expect(tierFromIsGlobal(true)).toBe('enterprise')
    expect(tierFromIsGlobal(false)).toBe('engagement')
  })
})
