import { describe, expect, it } from 'vitest'
import { proposedAriaLabel, proposedLabel, proposedVariant } from '../ProposedBadge.helpers'
import type { BaselineStanding } from '../../../domain/schemas/baselineStanding'

const BASELINE: BaselineStanding = { kind: 'enterprise-baseline' }

const proposed = (
  over: Partial<Extract<BaselineStanding, { kind: 'proposed' }>> = {},
): BaselineStanding => ({
  kind: 'proposed',
  proposal_ids: ['PCH@1780000000.aaaaaaa.rename'],
  changed_fields: ['name'],
  base_revision: '0f1e2d3c4b5a6978',
  condition: 'current',
  ...over,
})

describe('the proposed badge copy', () => {
  it('says nothing for the enterprise baseline', () => {
    // The ordinary case, and the badge renders on `proposedLabel` being non-null. A chip under every
    // artifact reading "unchanged" trains a reader to stop looking where the real answer appears.
    expect(proposedLabel(BASELINE)).toBeNull()
    expect(proposedVariant(BASELINE)).toBeNull()
    expect(proposedAriaLabel(BASELINE)).toBeNull()
  })

  it('names which fields differ, not merely that something does', () => {
    // The requirement a boolean could not meet: a reader must see *which parts* are local.
    const label = proposedLabel(proposed({ changed_fields: ['name', 'summary'] }))

    expect(label).toContain('name')
    expect(label).toContain('summary')
  })

  it('distinguishes a change awaiting review from one needing action', () => {
    expect(proposedVariant(proposed({ condition: 'current' }))).toBe('pending')
    expect(proposedVariant(proposed({ condition: 'stale' }))).toBe('attention')
    expect(proposedVariant(proposed({ condition: 'conflicting' }))).toBe('attention')
  })

  it('conveys a condition needing action in words, not by colour alone', () => {
    // `stale` and `conflicting` are the two states where the reader has to do something, so they
    // are the two that must not reach only the eye. The variant is a hint; the label is the statement.
    expect(proposedAriaLabel(proposed({ condition: 'stale' }))).toContain('stale')
    expect(proposedAriaLabel(proposed({ condition: 'conflicting' }))).toContain('conflicting')
    expect(proposedAriaLabel(proposed({ condition: 'current' }))).not.toContain('current')
  })

  it('counts the pending changes rather than saying "changes" for one', () => {
    expect(proposedAriaLabel(proposed())).toContain('one pending change')
    expect(proposedAriaLabel(proposed({ proposal_ids: ['a', 'b'] }))).toContain('2 pending changes')
  })

  it('says the artifact is not yet accepted upstream, in words', () => {
    // "Proposed" alone is jargon. What a reader needs is that this is not what the enterprise
    // repository holds.
    expect(proposedAriaLabel(proposed())).toContain('Not yet accepted upstream')
  })

  it('names every field in the label, however many there are', () => {
    const label = proposedLabel(proposed({ changed_fields: ['name', 'summary', 'status', 'keywords'] }))

    for (const field of ['name', 'summary', 'status', 'keywords']) {
      expect(label).toContain(field)
    }
  })
})
