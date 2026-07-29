import { describe, expect, it } from 'vitest'
import { mkDerivedAttribute } from '../../../domain/viewpointBindings'
import {
  addDerivedAttribute, ofHeadOptions, removeDerivedAttributeAt, updateDerivedAttributeAt,
} from '../QueryDerivedAttributesPanel.helpers'

const named = (name: string) => ({ ...mkDerivedAttribute(), name })

describe('addDerivedAttribute / removeDerivedAttributeAt / updateDerivedAttributeAt', () => {
  it('appends a fresh derived attribute', () => {
    expect(addDerivedAttribute([named('a')]).map((a) => a.name)).toEqual(['a', ''])
  })

  it('removes by index', () => {
    expect(removeDerivedAttributeAt([named('a'), named('b')], 0).map((a) => a.name)).toEqual(['b'])
  })

  it('patches only the targeted index', () => {
    const result = updateDerivedAttributeAt([named('a')], 0, { reduce: 'sum' })
    expect(result[0].reduce).toBe('sum')
  })
})

describe('ofHeadOptions', () => {
  it('excludes relationship-hops for a direct traversal', () => {
    expect(ofHeadOptions('direct')).toEqual(['none', 'connection', 'endpoint'])
  })

  it('includes relationship-hops only for a derived traversal', () => {
    expect(ofHeadOptions('derived')).toEqual(['none', 'connection', 'endpoint', 'relationship-hops'])
  })
})
