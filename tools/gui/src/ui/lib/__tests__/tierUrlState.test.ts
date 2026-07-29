import { describe, it, expect } from 'vitest'
import {
  LIST_TIERS,
  VIEWPOINT_TIERS,
  decodeTier,
  tierNeedsNormalization,
  withTier,
} from '../tierUrlState'

describe('decodeTier', () => {
  it.each([
    [{}, 'all'],
    [{ tier: 'engagement' }, 'engagement'],
    [{ tier: 'enterprise' }, 'enterprise'],
    [{ tier: 'module' }, 'all'], // disallowed on list surfaces
    [{ tier: 'global' }, 'all'], // never a URL value — internal identifier only
    [{ tier: 'ENTERPRISE' }, 'all'],
    [{ tier: '' }, 'all'],
    [{ tier: ['engagement', 'enterprise'] }, 'all'], // array values normalize to All
    [{ tier: null }, 'all'],
  ] as const)('list surface: %j → %s', (query, expected) => {
    expect(decodeTier(query as never, LIST_TIERS)).toBe(expected)
  })

  it('viewpoints additionally allow module', () => {
    expect(decodeTier({ tier: 'module' }, VIEWPOINT_TIERS)).toBe('module')
    expect(decodeTier({ tier: 'enterprise' }, VIEWPOINT_TIERS)).toBe('enterprise')
  })
})

describe('tierNeedsNormalization', () => {
  it('absent key is already canonical', () => {
    expect(tierNeedsNormalization({}, LIST_TIERS)).toBe(false)
  })

  it('valid values are canonical', () => {
    expect(tierNeedsNormalization({ tier: 'enterprise' }, LIST_TIERS)).toBe(false)
    expect(tierNeedsNormalization({ tier: 'module' }, VIEWPOINT_TIERS)).toBe(false)
  })

  it('disallowed, array, empty, and null values need one replace', () => {
    expect(tierNeedsNormalization({ tier: 'module' }, LIST_TIERS)).toBe(true)
    expect(tierNeedsNormalization({ tier: 'bogus' }, LIST_TIERS)).toBe(true)
    expect(tierNeedsNormalization({ tier: ['engagement'] }, LIST_TIERS)).toBe(true)
    expect(tierNeedsNormalization({ tier: '' }, LIST_TIERS)).toBe(true)
    expect(tierNeedsNormalization({ tier: null }, LIST_TIERS)).toBe(true)
  })
})

describe('withTier merge rules', () => {
  it('preserves unrelated query keys when setting a tier', () => {
    expect(withTier({ domain: 'motivation', view: 'treemap' }, 'enterprise')).toEqual({
      domain: 'motivation',
      view: 'treemap',
      tier: 'enterprise',
    })
  })

  it('removes the key entirely for All (absence = All)', () => {
    expect(withTier({ tier: 'enterprise', group: 'x' }, 'all')).toEqual({ group: 'x' })
  })

  it('replaces an invalid array value with the new selection', () => {
    expect(withTier({ tier: ['a', 'b'], group: 'x' }, 'engagement')).toEqual({
      tier: 'engagement',
      group: 'x',
    })
  })

  it('owns only the tier key — an existing tier is replaced, nothing else touched', () => {
    expect(withTier({ tier: 'engagement', doc_type: 'adr' }, 'enterprise')).toEqual({
      tier: 'enterprise',
      doc_type: 'adr',
    })
  })
})
