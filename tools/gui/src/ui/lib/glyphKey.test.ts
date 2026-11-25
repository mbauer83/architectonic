import { describe, expect, it } from 'vitest'
import { archimateGlyphMarkup } from './glyphKey'

/** The types the palette listed with the generic square before they had glyphs of their own (03·2). */
const UNMARKED = ['and-junction', 'or-junction', 'collaboration', 'grouping', 'location'] as const

describe('the glyph a type is drawn with', () => {
  it('gives each of the five unmarked types a glyph of its own, none the generic square', () => {
    const generic = archimateGlyphMarkup('no-such-type')
    const drawn = UNMARKED.map((type) => archimateGlyphMarkup(type))
    expect(drawn.every((markup) => markup !== null && markup !== generic)).toBe(true)
    expect(new Set(drawn).size).toBe(UNMARKED.length)
  })

  it('draws a marked type as before, an unknown one as the generic square, and nothing for none', () => {
    expect(archimateGlyphMarkup('business-actor')).toContain('circle')
    expect(archimateGlyphMarkup('no-such-type')).toContain('rect')
    expect(archimateGlyphMarkup(null)).toBeNull()
  })
})
