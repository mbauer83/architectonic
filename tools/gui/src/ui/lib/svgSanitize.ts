import DOMPurify from 'dompurify'

/**
 * DOMPurify's default `ALLOWED_URI_REGEXP` only permits a fixed list of known-safe URI schemes
 * (http(s), mailto, tel, …) plus relative references; it silently strips `href`/`xlink:href`
 * for anything else, including our own `arch://<artifact-id>` sentinel links that renderers
 * emit so the viewer can map an SVG element back to its artifact (see the activity diagram
 * type's `[[arch://…]]` links). Extending the allow-list is DOMPurify's documented mechanism
 * for admitting an application-specific scheme without weakening the rest of its URL sanitizing.
 *
 * This pattern must stay character-for-character equivalent to DOMPurify's own default
 * (`IS_ALLOWED_URI`) apart from the added `arch` scheme — DOMPurify applies it to EVERY
 * attribute value, not just hrefs. The escaped hyphens (`\-`) are load-bearing: written bare,
 * `.-:` becomes a character RANGE that swallows the digits 0-9, which makes any value starting
 * with a letter followed by a digit fail — i.e. every SVG path's `d="M307.9 …"` — silently
 * deleting all connector lines and entity-type icons from rendered diagrams.
 */
// eslint-disable-next-line no-useless-escape
export const ALLOWED_URI_REGEXP = /^(?:(?:(?:f|ht)tps?|mailto|tel|callto|sms|cid|xmpp|matrix|arch):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i

export function sanitizeDiagramSvg(svg: string): string {
  return DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
    ADD_ATTR: ['data-entity', 'data-entity-1', 'data-entity-2'],
    ALLOWED_URI_REGEXP,
  })
}
