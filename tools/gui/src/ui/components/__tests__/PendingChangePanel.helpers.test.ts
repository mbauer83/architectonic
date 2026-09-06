import { describe, expect, it } from 'vitest'
import type { ChangeSummary } from '../../../domain/schemas/changes'
import { changesAgainst } from '../PendingChangePanel.helpers'

const change = (over: Partial<ChangeSummary> = {}): ChangeSummary => ({
  artifact_id: 'PCH@1.a.change',
  target_id: 'STD@1.b.guidelines',
  target_name: 'General coding guidelines',
  reference_id: 'GAR@1.c.guidelines',
  kind: 'document',
  changed_fields: ['title'],
  state: 'draft',
  condition: 'current',
  divergence: [],
  ...over,
})

describe('the changes shown on one artifact', () => {
  it('matches the reference a reader of this repository holds', () => {
    expect(changesAgainst([change()], 'GAR@1.c.guidelines')).toHaveLength(1)
  })

  it('matches the enterprise id a reader of the promoted artifact holds', () => {
    // The admin deployment reads the artifact directly; matching only the reference would leave the
    // panel blank there, on an artifact that plainly carries a change.
    expect(changesAgainst([change()], 'STD@1.b.guidelines')).toHaveLength(1)
  })

  it('shows nothing for an artifact nothing is proposed against', () => {
    expect(changesAgainst([change()], 'REQ@1.d.something-else')).toEqual([])
  })

  it('keeps two changes against one artifact rather than picking one', () => {
    const both = [change(), change({ artifact_id: 'PCH@2.a.change' })]

    expect(changesAgainst(both, 'GAR@1.c.guidelines')).toHaveLength(2)
  })
})
