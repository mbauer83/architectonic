import glyphs from './archimateGlyphs.json'

/** Converts a camelCase ArchiMate type name to the kebab-case key used by ArchimateTypeGlyph. */
export const toGlyphKey = (t: string): string =>
  t.replace(/[A-Z]/g, (c, i) => (i > 0 ? '-' : '') + c.toLowerCase())

const kinds: Readonly<Record<string, string>> = glyphs.kinds
/**
 * Which glyph each type is drawn with. `types` is also the catalogue a rendered diagram marks its
 * elements by (the ontology's sprites); `unmarked_types` are the types a picker and a list still
 * need a glyph for but PlantUML draws with a shape of its own — a junction's dot, a grouping's
 * frame — so a diagram is not given a mark for them.
 */
const kindByType: Readonly<Record<string, string>> = { ...glyphs.unmarked_types, ...glyphs.types }

/** Inner SVG markup (viewBox 0 0 16) for an ArchiMate type's glyph, or null when the type is
 * absent. Entity ``artifact_type`` values are already kebab-case; unmapped types fall back to
 * the generic glyph. */
export const archimateGlyphMarkup = (typeName: string | null | undefined): string | null =>
  typeName ? kinds[kindByType[typeName] ?? 'generic'] ?? glyphs.kinds.generic : null
