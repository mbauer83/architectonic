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
