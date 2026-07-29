/**
 * Token-to-visual mapping convention for viewpoint style capabilities. `StyleRule.value`/
 * `RangeBand.value` are opaque tokens drawn from the fixed `STYLE_TOKENS` vocabulary
 * (`viewpointPresentation.ts`) — domain code never interprets them. This is the shared
 * surface adapter that resolves that vocabulary to a concrete visual per capability;
 * every surface (table badges, matrix cell emphasis, diagram overlay, exploration nodes)
 * reuses the same mapping so a token means the same thing everywhere.
 */

import type { StyleValue } from '../../domain/schemas/viewpoints'

export type StyleToken = 'emphasis' | 'positive' | 'caution' | 'critical' | 'neutral'

const TOKEN_COLORS: Record<StyleToken, string> = {
  emphasis: '#2563eb',
  positive: '#16a34a',
  caution: '#d97706',
  critical: '#dc2626',
  neutral: '#6b7280',
}

/** Named gradient-endpoint tokens for `mode: "scale"` rules: the distance pair
 * (`heat-near`/`heat-far`) and the magnitude pair (`heat-low`/`heat-high`) — the same
 * vocabulary `viewpoint_style_values.py` validates against. */
const SCALE_ENDPOINT_COLORS: Record<string, string> = {
  'heat-near': '#0891b2',
  'heat-far': '#dc2626',
  'heat-low': '#fbbf24',
  'heat-high': '#dc2626',
}

const HEX_COLOR = /^#[0-9a-f]{6}$/i

/** An explicit author-chosen `#rrggbb` style value, rendered as-is. */
export const isHexColorValue = (value: string): boolean => HEX_COLOR.test(value)

/** `node_color` / `edge_color` / `cluster_grouping`: a solid color swatch. A style value
 * is either a semantic token, a named scale endpoint, or an explicit `#rrggbb` color
 * literal (custom colors) — validated at save time, so an unknown value here means a
 * definition predating validation and falls back to neutral. */
export const tokenColor = (token: string): string =>
  isHexColorValue(token)
    ? token
    : TOKEN_COLORS[token as StyleToken] ?? SCALE_ENDPOINT_COLORS[token] ?? TOKEN_COLORS.neutral

export const SCALE_ENDPOINT_TOKENS: readonly string[] = Object.keys(SCALE_ENDPOINT_COLORS)

const TOKEN_SHAPES: Record<StyleToken, 'circle' | 'diamond' | 'triangle' | 'square'> = {
  emphasis: 'circle',
  positive: 'circle',
  caution: 'diamond',
  critical: 'triangle',
  neutral: 'square',
}

/** `node_shape`: the fixed-notation exploration node outline. */
export const tokenShape = (token: string): 'circle' | 'diamond' | 'triangle' | 'square' =>
  TOKEN_SHAPES[token as StyleToken] ?? TOKEN_SHAPES.neutral

const TOKEN_ICON_LETTERS: Record<StyleToken, string> = {
  emphasis: 'E', positive: '+', caution: '!', critical: '×', neutral: '·',
}

/** `node_icon`: a small corner-badge glyph (no icon font dependency). */
export const tokenIconLetter = (token: string): string => TOKEN_ICON_LETTERS[token as StyleToken] ?? '·'

export interface EdgeEmphasisStyle {
  readonly strokeWidth: number
  readonly dashArray: string | undefined
}

const TOKEN_EDGE_EMPHASIS: Record<StyleToken, EdgeEmphasisStyle> = {
  emphasis: { strokeWidth: 3, dashArray: undefined },
  positive: { strokeWidth: 2, dashArray: undefined },
  caution: { strokeWidth: 2.5, dashArray: '6 3' },
  critical: { strokeWidth: 4, dashArray: undefined },
  neutral: { strokeWidth: 1.5, dashArray: '2 3' },
}

/** `edge_emphasis`: stroke width + dash pattern. */
export const tokenEdgeEmphasis = (token: string): EdgeEmphasisStyle =>
  TOKEN_EDGE_EMPHASIS[token as StyleToken] ?? TOKEN_EDGE_EMPHASIS.neutral

export const STYLE_TOKEN_LABELS: Record<StyleToken, string> = {
  emphasis: 'Emphasis', positive: 'Positive', caution: 'Caution', critical: 'Critical', neutral: 'Neutral',
}

export const tokenLabel = (token: string): string => STYLE_TOKEN_LABELS[token as StyleToken] ?? token

export type Certainty = 'certain' | 'potential'

const CERTAINTY_DASH_ARRAYS: Record<Certainty, string> = { certain: '6 3', potential: '2 3' }

/** A derived (composed, never separately modeled) connection always renders dashed —
 * a fixed structural signal distinguishing it from a real modeled connection, independent
 * of any author-configured `edge_emphasis` style token. `certain` and `potential` use
 * different dash densities so the two are distinguishable without relying on color alone. */
export const certaintyDashArray = (certainty: Certainty | null): string | null =>
  certainty === null ? null : CERTAINTY_DASH_ARRAYS[certainty]

export const CERTAINTY_LABELS: Record<Certainty, string> = { certain: 'Certain', potential: 'Potential' }

const HEX_COMPONENT = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i

const hexToRgb = (hex: string): readonly [number, number, number] => {
  const match = HEX_COMPONENT.exec(hex)
  if (!match) return [107, 114, 128] // neutral gray fallback for an unparseable color
  return [parseInt(match[1], 16), parseInt(match[2], 16), parseInt(match[3], 16)]
}

const toHexByte = (n: number): string => Math.round(Math.max(0, Math.min(255, n))).toString(16).padStart(2, '0')

/** Linear RGB interpolation between two hex colors at `position` (clamped to [0, 1]). */
const interpolateHexColor = (from: string, to: string, position: number): string => {
  const clamped = Math.max(0, Math.min(1, position))
  const [r1, g1, b1] = hexToRgb(from)
  const [r2, g2, b2] = hexToRgb(to)
  const lerp = (a: number, b: number) => a + (b - a) * clamped
  return `#${toHexByte(lerp(r1, r2))}${toHexByte(lerp(g1, g2))}${toHexByte(lerp(b1, b2))}`
}

/** Resolves a per-item style value — a plain opaque token (match/range mode) or a
 * `{position, tokens}` scale-mode result — to one concrete color. A scale value is never
 * a discrete token: it always interpolates between its own two declared endpoints. */
export const resolveStyleColor = (value: StyleValue): string =>
  typeof value === 'string'
    ? tokenColor(value)
    : interpolateHexColor(tokenColor(value.tokens[0]), tokenColor(value.tokens[1]), value.position)

/** For capabilities needing one discrete token (`node_shape`/`node_icon`/`edge_emphasis`)
 * rather than an interpolated color — a scale-mode value has no natural single-token
 * reading, so this falls back to its near (lower-position) endpoint token. */
export const styleTokenString = (value: StyleValue): string => (typeof value === 'string' ? value : value.tokens[0])
