import { describe, expect, it } from 'vitest'
import { metadataInputValue, metadataWireValues } from './connectionMetadataValues'

describe('connection metadata value conversion', () => {
  it('preserves typed wire values when opening and saving the editor', () => {
    const inputs = {
      count: metadataInputValue(2),
      enabled: metadataInputValue(true),
      tags: metadataInputValue(['one', 'two']),
      label: metadataInputValue('relation'),
    }
    const wire = metadataWireValues(inputs, {
      count: { type: 'integer' },
      enabled: { type: 'boolean' },
      tags: { type: 'array' },
      label: { type: 'string' },
    })
    expect(wire).toEqual({ count: 2, enabled: true, tags: ['one', 'two'], label: 'relation' })
  })

  it('omits blank values', () => {
    expect(metadataWireValues({ polarity: '' }, { polarity: { type: 'string' } })).toEqual({})
  })

  it('preserves the type of metadata not covered by the current schema', () => {
    const original = { weight: 2, evidence: ['reviewed'] }
    expect(metadataWireValues({
      weight: metadataInputValue(original.weight),
      evidence: metadataInputValue(original.evidence),
    }, {}, original)).toEqual(original)
  })
})
