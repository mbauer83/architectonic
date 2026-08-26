import { describe, it, expect } from 'vitest'
import {
  tokenColor, tokenShape, tokenIconLetter, tokenEdgeEmphasis, tokenLabel, certaintyDashArray,
  resolveStyleColor, styleTokenString,
} from '../viewpointStyleTokens'

describe('viewpointStyleTokens', () => {
  it('resolves every fixed vocabulary token to a distinct color', () => {
    const tokens = ['emphasis', 'positive', 'caution', 'critical', 'neutral']
    const colors = tokens.map(tokenColor)
    expect(new Set(colors).size).toBe(tokens.length)
  })

  it('falls back to neutral for an unrecognized token', () => {
    expect(tokenColor('not-a-real-token')).toBe(tokenColor('neutral'))
    expect(tokenShape('not-a-real-token')).toBe(tokenShape('neutral'))
    expect(tokenEdgeEmphasis('not-a-real-token')).toEqual(tokenEdgeEmphasis('neutral'))
  })

  it('gives every token a non-empty icon letter and label', () => {
    for (const token of ['emphasis', 'positive', 'caution', 'critical', 'neutral']) {
      expect(tokenIconLetter(token).length).toBeGreaterThan(0)
      expect(tokenLabel(token).length).toBeGreaterThan(0)
    }
  })

  it('gives certain and potential distinct dash patterns, and null for a modeled connection', () => {
    expect(certaintyDashArray('certain')).not.toBe(certaintyDashArray('potential'))
    expect(certaintyDashArray(null)).toBeNull()
  })

  it('recognizes the real heat-near/heat-far scale endpoints as distinct colors, not the shared neutral fallback', () => {
    expect(tokenColor('heat-near')).not.toBe(tokenColor('heat-far'))
    expect(tokenColor('heat-near')).not.toBe(tokenColor('neutral'))
  })

  it('resolves a plain string style value the same as tokenColor', () => {
    expect(resolveStyleColor('critical')).toBe(tokenColor('critical'))
  })

  it('resolves a scale value to its first endpoint color at position 0 and second at position 1', () => {
    expect(resolveStyleColor({ position: 0, tokens: ['heat-near', 'heat-far'] })).toBe(tokenColor('heat-near'))
    expect(resolveStyleColor({ position: 1, tokens: ['heat-near', 'heat-far'] })).toBe(tokenColor('heat-far'))
  })

  it('interpolates a scale value at an intermediate position to a color between the two endpoints', () => {
    const near = tokenColor('heat-near')
    const far = tokenColor('heat-far')
    const mid = resolveStyleColor({ position: 0.5, tokens: ['heat-near', 'heat-far'] })
    expect(mid).not.toBe(near)
    expect(mid).not.toBe(far)
    expect(mid).toMatch(/^#[0-9a-f]{6}$/)
  })

  it('clamps an out-of-range scale position instead of extrapolating', () => {
    expect(resolveStyleColor({ position: -5, tokens: ['heat-near', 'heat-far'] })).toBe(tokenColor('heat-near'))
    expect(resolveStyleColor({ position: 5, tokens: ['heat-near', 'heat-far'] })).toBe(tokenColor('heat-far'))
  })

  it('styleTokenString reads a plain string as-is and falls back to a scale value\'s near-end token', () => {
    expect(styleTokenString('critical')).toBe('critical')
    expect(styleTokenString({ position: 0.7, tokens: ['heat-near', 'heat-far'] })).toBe('heat-near')
  })
})

/**
 * The browser half of a cross-language conformance pair. The other half is
 * `tests/architecture/test_every_style_token_has_a_colour.py`, whose `RAMP_SAMPLES` holds these same
 * values and asserts the server's `interpolate_style_colors` produces them.
 *
 * Two implementations, two languages, neither able to call the other — and both now render the same
 * rule. The server resolves a scale position to a colour for a diagram element; this adapter resolves
 * it for a table badge, a matrix cell and an exploration node. A ramp read one way on the picture and
 * another in the table shows one rule as two colours, so what has to agree is the convention:
 * component-wise linear interpolation in sRGB, position clamped to [0, 1]. The way to hold two
 * languages to a convention is to write down what it produces and check both sides against it.
 *
 * If a sample changes here it must change there in the same commit.
 */
const RAMP_SAMPLES: readonly (readonly [string, string, number, string])[] = [
  ['heat-low', 'heat-high', 0.0, '#fbbf24'],
  ['heat-low', 'heat-high', 0.5, '#ec7325'],
  ['heat-low', 'heat-high', 1.0, '#dc2626'],
  ['heat-low', 'heat-high', -1.0, '#fbbf24'],
  ['heat-low', 'heat-high', 2.0, '#dc2626'],
  ['heat-near', 'heat-far', 0.25, '#3d768f'],
]

describe('the ramp convention', () => {
  it.each(RAMP_SAMPLES)('resolves %s→%s at %d to %s', (near, far, position, expected) => {
    expect(resolveStyleColor({ position, tokens: [near, far] }).toLowerCase()).toBe(expected)
  })
})
