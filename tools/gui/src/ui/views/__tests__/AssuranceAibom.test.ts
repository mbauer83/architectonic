import { describe, it, expect } from 'vitest'
import {
  parseCandidates,
  parseCoverage,
  scoreBand,
  componentHasBlockingGap,
} from '../AssuranceAibom.helpers'

describe('parseCandidates', () => {
  it('decodes candidates and coerces fields', () => {
    const out = parseCandidates({
      candidates: [
        {
          entity_id: 'APP@1', name: 'Claude', entity_type: 'application-component',
          score: 55, reasons: ['LLM name pattern'],
        },
        { entity_id: 'APP@2', name: 'X', entity_type: 't', score: 'bad', reasons: 'bad' },
      ],
    })
    expect(out).toHaveLength(2)
    expect(out[0].score).toBe(55)
    expect(out[1].score).toBe(0)
    expect(out[1].reasons).toEqual([])
  })

  it('returns empty when candidates is absent or malformed', () => {
    expect(parseCandidates({})).toEqual([])
    expect(parseCandidates({ candidates: 'nope' })).toEqual([])
    expect(parseCandidates(null)).toEqual([])
  })
})

describe('parseCoverage', () => {
  it('decodes per-component gaps and unbound roles', () => {
    const cov = parseCoverage({
      components: [
        {
          entity_id: 'APP@1', name: 'Model', specialization: 'ai-model',
          missing_required_attributes: ['Task'], missing_recommended_attributes: ['Approach'],
          missing_dataset_linkage: true, missing_governance: false,
        },
      ],
      unbound_roles: ['governed-by'],
    })
    expect(cov.components).toHaveLength(1)
    expect(cov.components[0].missing_required_attributes).toEqual(['Task'])
    expect(cov.components[0].missing_dataset_linkage).toBe(true)
    expect(cov.unbound_roles).toEqual(['governed-by'])
  })

  it('is empty and total on a malformed or empty body', () => {
    expect(parseCoverage(null)).toEqual({ components: [], unbound_roles: [] })
    expect(parseCoverage({ components: 'nope' })).toEqual({ components: [], unbound_roles: [] })
  })
})

describe('componentHasBlockingGap', () => {
  const base = {
    entity_id: 'A', name: 'n', specialization: 'ai-model',
    missing_required_attributes: [] as string[], missing_recommended_attributes: [] as string[],
    missing_dataset_linkage: false, missing_governance: false,
  }

  it('is false when nothing blocking is missing (advisory does not count)', () => {
    expect(componentHasBlockingGap({ ...base, missing_recommended_attributes: ['Approach'] })).toBe(false)
  })

  it('is true for a missing required attribute, dataset link, or governance', () => {
    expect(componentHasBlockingGap({ ...base, missing_required_attributes: ['Task'] })).toBe(true)
    expect(componentHasBlockingGap({ ...base, missing_dataset_linkage: true })).toBe(true)
    expect(componentHasBlockingGap({ ...base, missing_governance: true })).toBe(true)
  })
})

describe('scoreBand', () => {
  it('bands scores into high/medium/low', () => {
    expect(scoreBand(70)).toBe('high')
    expect(scoreBand(50)).toBe('high')
    expect(scoreBand(35)).toBe('medium')
    expect(scoreBand(30)).toBe('medium')
    expect(scoreBand(10)).toBe('low')
  })
})
