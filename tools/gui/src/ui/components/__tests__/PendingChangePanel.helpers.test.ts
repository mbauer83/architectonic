import { describe, expect, it } from 'vitest'
import type { ChangeSummary } from '../../../domain/schemas/changes'
import { changesAgainst } from '../PendingChangePanel.helpers'

const change = (over: Partial<ChangeSummary> = {}): ChangeSummary => ({
  artifact_id: 'PCH@1.a.change',
  target_id: 'STD@1.b.guidelines',
  target_name: 'General coding guidelines',
  kind: 'document',
  changed_fields: ['title'],
  state: 'draft',
  condition: 'current',
  divergence: [],
  ...over,
})

describe('the changes shown on one artifact', () => {
  it('matches the promoted artifact, which is the page a reader is on', () => {
    expect(changesAgainst([change()], 'STD@1.b.guidelines')).toHaveLength(1)
  })

  it('does not match the reference, which no reachable page is addressed by', () => {
    // A reference is machinery: excluded from every list and every search, so matching it would be
    // a second place that had to know references exist.
    expect(changesAgainst([change()], 'GAR@1.c.guidelines')).toEqual([])
  })

  it('shows nothing for an artifact nothing is proposed against', () => {
    expect(changesAgainst([change()], 'REQ@1.d.something-else')).toEqual([])
  })

  it('keeps two changes against one artifact rather than picking one', () => {
    const both = [change(), change({ artifact_id: 'PCH@2.a.change' })]

    expect(changesAgainst(both, 'STD@1.b.guidelines')).toHaveLength(2)
  })
})
