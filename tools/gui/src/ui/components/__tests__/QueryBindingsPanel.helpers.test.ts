import { describe, expect, it } from 'vitest'
import { mkQueryBinding } from '../../../domain/viewpointBindings'
import { addBinding, canIncludeInResult, earlierBindingNames, removeBindingAt, updateBindingAt } from '../QueryBindingsPanel.helpers'

const named = (name: string) => ({ ...mkQueryBinding(), name })

describe('earlierBindingNames', () => {
  it('is empty for the first binding', () => {
    expect(earlierBindingNames([named('a'), named('b')], 0)).toEqual([])
  })

  it('lists only strictly-earlier declared names, never itself or later ones', () => {
    expect(earlierBindingNames([named('a'), named('b'), named('c')], 2)).toEqual(['a', 'b'])
  })

  it('skips a not-yet-named earlier binding (empty name is not a valid reference target)', () => {
    expect(earlierBindingNames([named(''), named('b')], 2)).toEqual(['b'])
  })
})

describe('addBinding / removeBindingAt / updateBindingAt', () => {
  it('appends a fresh binding', () => {
    const result = addBinding([named('a')])
    expect(result.map((b) => b.name)).toEqual(['a', ''])
  })

  it('removes by index', () => {
    expect(removeBindingAt([named('a'), named('b')], 0).map((b) => b.name)).toEqual(['b'])
  })

  it('patches only the targeted index', () => {
    const result = updateBindingAt([named('a'), named('b')], 1, { name: 'renamed' })
    expect(result.map((b) => b.name)).toEqual(['a', 'renamed'])
  })
})

describe('canIncludeInResult', () => {
  it('is true for a plain entities selection', () => {
    expect(canIncludeInResult(named('a'))).toBe(true)
  })

  it('is false for a connections selection', () => {
    expect(canIncludeInResult({ ...named('a'), select: 'connections' })).toBe(false)
  })

  it('is false once projected or aggregated (no longer entity-valued)', () => {
    expect(canIncludeInResult({ ...named('a'), project: 'name' })).toBe(false)
    expect(canIncludeInResult({ ...named('a'), aggregate: 'count' })).toBe(false)
  })

  it('is false for a tuple binding', () => {
    expect(canIncludeInResult({ ...named('a'), mode: 'tuple' })).toBe(false)
  })
})
