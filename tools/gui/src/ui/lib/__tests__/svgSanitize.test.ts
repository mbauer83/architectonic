// @vitest-environment jsdom
//
// jsdom (not the suite's default node env) is required here: without a DOM, DOMPurify reports
// isSupported=false and returns its input UNCHANGED — a sanitize test in the node env passes
// vacuously no matter how broken the config is. That gap is exactly how a config regression
// (an unescaped hyphen turning `.-:` into a digit-swallowing character range) shipped and
// silently stripped every `d="M…"` path attribute — all connector lines and entity-type icons —
// from rendered diagrams.
import { describe, it, expect } from 'vitest'
import { sanitizeDiagramSvg, ALLOWED_URI_REGEXP } from '../svgSanitize'

/** Trimmed-down but structurally faithful PlantUML output: geometry via path `d` (letter-then-
 * digit values), polygon `points`, stroke styling in `style` attributes, and an activity
 * sentinel link. */
const PLANTUML_SVG = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 785 1247"><?plantuml 1.2026.3?><defs/><g>
<rect fill="#FAFAFA" height="1247" style="stroke:none;stroke-width:1;" width="785" x="0" y="0"/>
<g class="entity" data-source-line="70">
<path d="M307.9264,91.9738 L316.6495,91.9738 L322.8802,97.3738 Z" fill="#252327" style="stroke:#181818;stroke-width:0.5;"/>
<path d="m12.5,3 c-1.9,0 -3.5,1.6 -3.5,3.5 z" fill="none" style="stroke:#8C7E6A;stroke-width:1;"/>
<polygon fill="#181818" points="217,247.1869,221,238.1869,217,242.1869,213,238.1869" style="stroke:#181818;stroke-width:1;"/>
<text fill="#000000" font-family="sans-serif" font-size="14" lengthAdjust="spacing" textLength="100" x="10" y="20">Label</text>
<a href="arch://REQ@1.a.x" target="_top"><rect x="1" y="1" width="10" height="10" fill="#fff"/></a>
</g></g></svg>`

describe('sanitizeDiagramSvg (full pipeline, real DOM)', () => {
  const out = sanitizeDiagramSvg(PLANTUML_SVG)

  it('preserves every path geometry (d attributes) — connector lines and type icons', () => {
    expect((out.match(/ d="/g) ?? []).length).toBe(2)
    expect(out).toContain('M307.9264,91.9738')
    expect(out).toContain('m12.5,3')
  })

  it('preserves polygon points, stroke styles, and text metrics', () => {
    expect(out).toContain('points="217,247.1869')
    expect((out.match(/style="stroke:/g) ?? []).length).toBe(4)
    expect(out).toContain('textLength="100"')
  })

  it('preserves viewer mapping hooks (class, data-source-line, arch: sentinel links)', () => {
    expect(out).toContain('class="entity"')
    expect(out).toContain('data-source-line="70"')
    expect(out).toContain('href="arch://REQ@1.a.x"')
  })

  it('still strips active content and script-scheme links', () => {
    const hostile = PLANTUML_SVG.replace(
      '</g></g></svg>',
      '<script>alert(1)</script><a href="javascript:alert(1)"><rect/></a></g></g></svg>',
    )
    const cleaned = sanitizeDiagramSvg(hostile)
    expect(cleaned).not.toContain('<script')
    expect(cleaned).not.toContain('javascript:')
  })
})

describe('ALLOWED_URI_REGEXP', () => {
  it('accepts SVG path data — DOMPurify applies this regexp to EVERY attribute value', () => {
    // Letter-then-digit values are the regression trigger: with an unescaped hyphen the
    // class range [.-:] contains 0-9 and these fail.
    expect(ALLOWED_URI_REGEXP.test('M307.9264,91.9738L316.6495,91.9738')).toBe(true)
    expect(ALLOWED_URI_REGEXP.test('m12.5,3c-1.9,0-3.5,1.6-3.5,3.5z')).toBe(true)
  })

  it('allows the arch: sentinel scheme', () => {
    expect(ALLOWED_URI_REGEXP.test('arch://a1')).toBe(true)
  })

  it('still allows the schemes DOMPurify permits by default', () => {
    expect(ALLOWED_URI_REGEXP.test('https://example.com')).toBe(true)
    expect(ALLOWED_URI_REGEXP.test('mailto:a@b.com')).toBe(true)
  })

  it('still blocks unlisted schemes', () => {
    expect(ALLOWED_URI_REGEXP.test('javascript:alert(1)')).toBe(false)
    expect(ALLOWED_URI_REGEXP.test('data:text/html,<script>')).toBe(false)
  })
})
