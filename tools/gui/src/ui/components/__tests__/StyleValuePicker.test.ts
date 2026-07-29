import { describe, expect, it } from 'vitest'
import { customColorFor, isCustomSelection, pickerSwatches } from '../StyleValuePicker.helpers'
import { tokenColor } from '../../lib/viewpointStyleTokens'

describe('pickerSwatches', () => {
  it('offers exactly the five semantic tokens by default', () => {
    expect(pickerSwatches(false).map((s) => s.token))
      .toEqual(['emphasis', 'positive', 'caution', 'critical', 'neutral'])
  })

  it('appends the four named scale endpoints when allowed', () => {
    const tokens = pickerSwatches(true).map((s) => s.token)
    expect(tokens.slice(0, 5)).toEqual(['emphasis', 'positive', 'caution', 'critical', 'neutral'])
    expect(tokens.slice(5)).toEqual(['heat-near', 'heat-far', 'heat-low', 'heat-high'])
  })

  it('resolves each swatch to its renderer color and a human label', () => {
    const positive = pickerSwatches(false).find((s) => s.token === 'positive')
    expect(positive).toEqual({ token: 'positive', color: tokenColor('positive'), label: 'Positive' })
  })
})

describe('isCustomSelection', () => {
  it('selects the custom swatch for an explicit hex value', () => {
    expect(isCustomSelection('#a1b2c3')).toBe(true)
    expect(isCustomSelection('#A1B2C3')).toBe(true)
  })

  it('does not select custom for tokens, endpoints, null, or malformed hex', () => {
    expect(isCustomSelection('critical')).toBe(false)
    expect(isCustomSelection('heat-near')).toBe(false)
    expect(isCustomSelection(null)).toBe(false)
    expect(isCustomSelection('#fff')).toBe(false)
    expect(isCustomSelection('a1b2c3')).toBe(false)
  })
})

describe('customColorFor', () => {
  it('preloads the color input with the current hex value', () => {
    expect(customColorFor('#a1b2c3')).toBe('#a1b2c3')
  })

  it('falls back to a fixed starting color for non-hex values', () => {
    expect(customColorFor('critical')).toBe('#8b5cf6')
    expect(customColorFor(null)).toBe('#8b5cf6')
  })
})
