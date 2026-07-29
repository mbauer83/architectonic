import glyphs from './archimateGlyphs.json'

/** Converts a camelCase ArchiMate type name to the kebab-case key used by ArchimateTypeGlyph. */
export const toGlyphKey = (t: string): string =>
  t.replace(/[A-Z]/g, (c, i) => (i > 0 ? '-' : '') + c.toLowerCase())

/** Inner SVG markup (viewBox 0 0 16) for an ArchiMate type's glyph, or null when the type is
 * unknown/absent. Entity ``artifact_type`` values are already kebab-case and key
 * ``glyphs.types`` directly; unmapped types fall back to the generic glyph. */
export const archimateGlyphMarkup = (typeName: string | null | undefined): string | null => {
  if (!typeName) return null
  const kind = glyphs.types[typeName as keyof typeof glyphs.types] ?? 'generic'
  return glyphs.kinds[kind as keyof typeof glyphs.kinds] ?? glyphs.kinds.generic ?? null
}
