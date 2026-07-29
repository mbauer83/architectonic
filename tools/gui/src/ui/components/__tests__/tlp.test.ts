import { describe, it, expect } from 'vitest'
import { tlpColor } from '../tlp'

describe('tlpColor', () => {
  it('maps each TLP level to a distinct colour (not a single red)', () => {
    const white = tlpColor('TLP:WHITE')
    const green = tlpColor('TLP:GREEN')
    const amber = tlpColor('TLP:AMBER')
    const red = tlpColor('TLP:RED')
    const colours = new Set([white, green, amber, red])
    expect(colours.size).toBe(4)
    expect(red).toBe('#dc2626')
    expect(green).toBe('#15803d')
    expect(amber).toBe('#b45309')
  })

  it('treats CLEAR like WHITE and is case-insensitive', () => {
    expect(tlpColor('TLP:CLEAR')).toBe(tlpColor('TLP:WHITE'))
    expect(tlpColor('tlp:red')).toBe('#dc2626')
  })

  it('falls back to neutral grey for unknown/empty values', () => {
    expect(tlpColor(undefined)).toBe('#475569')
    expect(tlpColor('')).toBe('#475569')
    expect(tlpColor('bogus')).toBe('#475569')
  })
})
