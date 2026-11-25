import { describe, expect, it } from 'vitest'
import { connectionTypeLabel } from '../connectionTypeLabel'

describe('connectionTypeLabel', () => {
  it('drops the meta-ontology prefix', () => {
    expect(connectionTypeLabel('archimate-serving')).toBe('serving')
  })

  it('leaves an unprefixed type alone', () => {
    expect(connectionTypeLabel('c4-uses')).toBe('c4-uses')
  })
})
