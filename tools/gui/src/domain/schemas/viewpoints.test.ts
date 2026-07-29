import { Schema } from 'effect'
import { describe, expect, it } from 'vitest'
import { ProjectedOccurrenceSchema } from './viewpoints'

describe('ProjectedOccurrenceSchema', () => {
  it('decodes a plain string style value (match/range mode)', () => {
    const raw = {
      item_id: 'ENT@a', item_kind: 'entity', state: 'visible', membership: 'primary',
      reasons: [], style: { node_color: 'critical' },
    }
    const decoded = Schema.decodeUnknownSync(ProjectedOccurrenceSchema)(raw)
    expect(decoded.style.node_color).toBe('critical')
  })

  it('decodes a scale-mode {position, tokens} style value — regression: this real backend shape (captured live from element-dependents execution) previously failed decoding entirely because the schema only accepted strings', () => {
    const raw = {
      item_id: 'ACT@1712870400.Pp8Qq8.developer', item_kind: 'entity', state: 'visible', membership: 'expanded',
      reasons: [],
      style: { node_color: { position: 0.3333333333333333, tokens: ['heat-near', 'heat-far'] } },
    }
    const decoded = Schema.decodeUnknownSync(ProjectedOccurrenceSchema)(raw)
    expect(decoded.style.node_color).toEqual({ position: 0.3333333333333333, tokens: ['heat-near', 'heat-far'] })
  })
})
