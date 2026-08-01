import { describe, it, expect } from 'vitest'
import {
  parseCandidates,
  parseCoverage,
  scoreBand,
  componentHasBlockingGap,
} from '../AssuranceAibom.helpers'

describe('parseCandidates', () => {
  it('decodes the candidates the route sends', () => {
    const out = parseCandidates({
      candidates: [
        {
          entity_id: 'APP@1', name: 'Claude', entity_type: 'application-component',
          score: 55, reasons: ['LLM name pattern'],
        },
      ],
      count: 1,
      note: 'Heuristic suggestions only.',
    })

    expect(out).toHaveLength(1)
    expect(out[0].score).toBe(55)
    expect(out[0].reasons).toEqual(['LLM name pattern'])
  })

  it('refuses a body that does not match the contract, rather than emptying it', () => {
    /* These used to coerce: a string score became 0, a string `reasons` became [], and an absent
       `candidates` key became an empty scan. Every one of those reads as a real answer — "no AI
       components found" is a conclusion an operator would act on — so the contract turning them into
       a failure is the point of having one. */
    expect(() => parseCandidates({})).toThrow()
    expect(() => parseCandidates({ candidates: 'nope', count: 0, note: '' })).toThrow()
    expect(() => parseCandidates(null)).toThrow()
    expect(() => parseCandidates({
      candidates: [{ entity_id: 'A', name: 'X', entity_type: 't', score: 'bad', reasons: [] }],
      count: 1,
      note: '',
    })).toThrow()
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

  it('refuses a malformed body rather than reporting clean coverage', () => {
    /* The dangerous coercion of the three: an unreadable body became `{components: [], unbound_roles:
       []}`, which is precisely the shape of a repository with no gaps at all. */
    expect(() => parseCoverage(null)).toThrow()
    expect(() => parseCoverage({ components: 'nope', unbound_roles: [] })).toThrow()
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
