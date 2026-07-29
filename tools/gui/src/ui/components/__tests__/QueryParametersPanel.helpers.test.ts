import { describe, expect, it } from 'vitest'
import { mkQueryParameter } from '../../../domain/viewpointBindings'
import { addParameter, removeParameterAt, updateParameterAt } from '../QueryParametersPanel.helpers'

const named = (name: string) => ({ ...mkQueryParameter(), name })

describe('addParameter / removeParameterAt / updateParameterAt', () => {
  it('appends a fresh parameter', () => {
    expect(addParameter([named('a')]).map((p) => p.name)).toEqual(['a', ''])
  })

  it('removes by index', () => {
    expect(removeParameterAt([named('a'), named('b')], 1).map((p) => p.name)).toEqual(['a'])
  })

  it('patches only the targeted index', () => {
    const result = updateParameterAt([named('a'), named('b')], 0, { required: false })
    expect(result[0].required).toBe(false)
    expect(result[1].required).toBe(true)
  })
})
