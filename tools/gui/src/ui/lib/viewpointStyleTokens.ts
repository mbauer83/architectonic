/**
 * Token-to-visual mapping convention for viewpoint style capabilities. `StyleRule.value`/
 * `RangeBand.value` are opaque tokens drawn from the fixed `STYLE_TOKENS` vocabulary
 * (`viewpointPresentation.ts`) — nothing interprets one except a surface adapter. This is the
 * browser's adapter: table badges, matrix cell emphasis, exploration nodes and the execution
 * overlay all resolve through it, so a token means the same thing on every one of them.
 *
 * It is no longer the *only* adapter. An ad-hoc reading lens renders diagrams server-side, so the
 * renderer resolves tokens too — which is why the palette below is read from the generated constants
 * instead of written here. One table, two adapters; the contract that a token is opaque to domain
 * code is unchanged, and the table is not domain code interpreting a token but the declaration of
 * what the token *is*.
 */

import { SCALE_ENDPOINT_ORDER, STYLE_TOKEN_COLORS } from '../../domain/types.generated'
import type { StyleValue } from '../../domain/schemas/viewpoints'

export type StyleToken = 'emphasis' | 'positive' | 'caution' | 'critical' | 'neutral'

/** The token palette, read from the generated constants rather than restated here.
 *
 * It was a literal in this file while every renderer of a token was a browser. An ad-hoc reading lens
 * renders server-side — it may re-layout, and it must export to SVG and PNG — so the diagram renderer
 * resolves tokens too, and a literal here would be the second of two palettes that can disagree.
 * That is the incident `DOMAIN_COLORS` records, and this follows the arrangement it established:
 * declared once on the server, generated into these constants, read by every adapter. */
const TOKEN_COLORS: Record<string, string> = STYLE_TOKEN_COLORS

/** The named scale endpoints — the distance pair (`heat-near`/`heat-far`) and the magnitude pair
 * (`heat-low`/`heat-high`), the same vocabulary `viewpoint_style_values.py` validates against, from
 * the same generated table. Kept as its own view of it because
 * `SCALE_ENDPOINT_TOKENS` below is what the endpoint picker offers, and a scale endpoint is a
 * different question from a semantic token even though both resolve through one palette. */
const SCALE_ENDPOINT_COLORS: Record<string, string> = Object.fromEntries(
  SCALE_ENDPOINT_ORDER.map((token) => [token, STYLE_TOKEN_COLORS[token]]),
)

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

/** The endpoints an author is offered, in the order they are declared — the distance pair then the
 * magnitude pair, each pair's near end first. Read from the generated sequence rather than from the
 * palette's keys: a palette is a lookup and its key order is alphabetical, which scrambles the pairs.
 */
export const SCALE_ENDPOINT_TOKENS: readonly string[] = SCALE_ENDPOINT_ORDER

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
