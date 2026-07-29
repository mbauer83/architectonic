import { Schema } from 'effect'
import { describe, expect, it } from 'vitest'
import { PatternResultSchema } from './viewpointTrace'

const decode = Schema.decodeUnknownSync(PatternResultSchema)

describe('PatternResultSchema', () => {
  it('decodes a diagnostic result from its discriminator-specific wire shape', () => {
    expect(decode({
      role: 'diagnostic',
      observation: 'none_observed',
      last_satisfied_ids: [],
    })).toEqual({
      role: 'diagnostic',
      observation: 'none_observed',
      last_satisfied_ids: [],
    })
  })

  it('still requires status_code for an authoritative result', () => {
    expect(() => decode({
      role: 'authoritative',
      verdict: 'gap',
      coverage: { covered: 0, applicable: 1 },
      incomplete_branch_count: 1,
      failing_obligations: [],
      failing_overflow: 0,
      last_satisfied_ids: [],
      missing_expected: ['requirement'],
      shortcut: false,
    })).toThrow()
  })
})
