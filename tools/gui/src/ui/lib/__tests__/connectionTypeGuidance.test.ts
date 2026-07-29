import { describe, it, expect } from 'vitest'
import { connectionCreationGuidance, connectionTypeLabel } from '../connectionTypeGuidance'
import type { AuthoringGuidance } from '../../../domain'

/**
 * Relationship creation guidance is read from the same payload the forms already hold, and is
 * absent — not blank — whenever there is nothing to say, so a wizard row never discloses an empty
 * hint (guidance ships empty until an import has run).
 */
const guidance = (connectionTypes: unknown[]): AuthoringGuidance =>
  ({ connection_types: connectionTypes } as unknown as AuthoringGuidance)

describe('connectionCreationGuidance', () => {
  it('returns the type\'s create/never pair', () => {
    const result = connectionCreationGuidance(
      guidance([{ name: 'archimate-serving', create_when: 'cw', never_create_when: 'nw', specializations: [] }]),
      'archimate-serving',
    )
    expect(result).toEqual({ createWhen: 'cw', neverCreateWhen: 'nw' })
  })

  it('returns null for a type absent from the payload', () => {
    const result = connectionCreationGuidance(
      guidance([{ name: 'archimate-serving', create_when: 'cw', specializations: [] }]),
      'archimate-flow',
    )
    expect(result).toBeNull()
  })

  it('returns null when the type carries no guidance text', () => {
    const result = connectionCreationGuidance(
      guidance([{ name: 'archimate-serving', create_when: '', never_create_when: '   ', specializations: [] }]),
      'archimate-serving',
    )
    expect(result).toBeNull()
  })

  it('keeps a one-sided pair', () => {
    const result = connectionCreationGuidance(
      guidance([{ name: 'archimate-flow', never_create_when: 'nw only', specializations: [] }]),
      'archimate-flow',
    )
    expect(result).toEqual({ createWhen: '', neverCreateWhen: 'nw only' })
  })

  it('returns null without any guidance payload', () => {
    expect(connectionCreationGuidance(null, 'archimate-serving')).toBeNull()
  })
})

describe('connectionTypeLabel', () => {
  it('drops the meta-ontology prefix', () => {
    expect(connectionTypeLabel('archimate-serving')).toBe('serving')
  })

  it('leaves an unprefixed type alone', () => {
    expect(connectionTypeLabel('c4-uses')).toBe('c4-uses')
  })
})
