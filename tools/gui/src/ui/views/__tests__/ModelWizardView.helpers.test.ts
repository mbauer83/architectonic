import { describe, it, expect } from 'vitest'
import { buildWizardDomainCards, recommendedNextDomain } from '../ModelWizardView.helpers'

describe('buildWizardDomainCards', () => {
  it('scopes to ArchiMate domains only (excludes sysml)', () => {
    const cards = buildWizardDomainCards({}, null, [{ name: 'archimate-4-0' }])
    const keys = cards.map((c) => c.key)
    expect(keys).toEqual(['motivation', 'strategy', 'business', 'common', 'application', 'technology', 'implementation'])
    expect(keys).not.toContain('sysml')
  })

  it('carries the created count for a domain with progress', () => {
    const cards = buildWizardDomainCards({ motivation: 3 })
    expect(cards.find((c) => c.key === 'motivation')?.createdCount).toBe(3)
  })

  it('defaults an unmentioned domain to zero', () => {
    const cards = buildWizardDomainCards({ motivation: 3 })
    expect(cards.find((c) => c.key === 'business')?.createdCount).toBe(0)
  })

  it('every card has a non-empty label, color, and intro', () => {
    for (const card of buildWizardDomainCards({})) {
      expect(card.label.length).toBeGreaterThan(0)
      expect(card.color.length).toBeGreaterThan(0)
      expect(card.intro.length, card.key).toBeGreaterThan(0)
    }
  })

  it('marks exactly the recommended domain', () => {
    const cards = buildWizardDomainCards({ application: 1 }, 'application')
    expect(cards.filter((c) => c.recommended).map((c) => c.key)).toEqual(['common'])
  })
})

describe('recommendedNextDomain (omnidirectional, D-7)', () => {
  it('defaults a fresh session to motivation', () => {
    expect(recommendedNextDomain({})).toBe('motivation')
    expect(recommendedNextDomain({}, null)).toBe('motivation')
  })

  it('recommends the untouched spine neighbor of where the user just worked', () => {
    expect(recommendedNextDomain({ application: 1 }, 'application')).toBe('common')
    expect(recommendedNextDomain({ motivation: 2 }, 'motivation')).toBe('business')
    expect(recommendedNextDomain({ common: 1, application: 1 }, 'common')).toBe('business')
  })

  it('prefers the forward neighbor when both are untouched', () => {
    expect(recommendedNextDomain({ business: 1 }, 'business')).toBe('common')
  })

  it('falls back to the first untouched spine domain when neighbors are covered', () => {
    expect(recommendedNextDomain({ business: 1, common: 1, application: 1 }, 'common'))
      .toBe('motivation')
  })

  it('recommends nothing once every spine domain has content', () => {
    const counts = { motivation: 1, business: 1, common: 1, application: 1 }
    expect(recommendedNextDomain(counts, 'application')).toBeNull()
    expect(buildWizardDomainCards(counts, 'application').some((c) => c.recommended)).toBe(false)
  })

  it('ignores off-spine progress (technology does not satisfy the spine)', () => {
    expect(recommendedNextDomain({ technology: 5 })).toBe('motivation')
  })
})
