import { Effect } from 'effect'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { type ArtifactArea } from '../domain/artifactLinks'
import { artifactRouteForHref } from '../ui/router/artifactLinkRoutes'

export class MarkdownError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'MarkdownError'
  }
}

/**
 * Area of the artifact currently being rendered, for links that name no area of their own.
 *
 * Module-scoped rather than a parameter because the rewrite is a `walkTokens` hook on the shared
 * `marked` instance, registered once, which receives only the token. Safe because rendering is
 * synchronous (`async: false`): the value is set and cleared around a single parse that cannot
 * interleave with another.
 */
let siblingArea: ArtifactArea | undefined

// Repository-relative artifact links would otherwise resolve against the current
// GUI route and 404 — rewrite them to their in-app routes at token level, before
// rendering. Registered once, on the shared marked instance.
marked.use({
  walkTokens: (token) => {
    if (token.type === 'link' && typeof token.href === 'string') {
      const route = artifactRouteForHref(token.href, siblingArea)
      if (route !== null) token.href = route
    }
  },
})

/**
 * Keep a tag the allowlist rejects, as visible text.
 *
 * DOMPurify removes an element it does not know and keeps its children. An element with no children
 * therefore disappeared entirely, and repository prose is full of them: `projects/<slug>/model/`
 * rendered as `projects//model/`, with nothing to say that anything had been dropped. Angle brackets
 * in this corpus are placeholders — path shapes, ArchiMate type names, id forms — so a rejected tag is
 * authored text and deleting it loses content silently.
 *
 * The sanitiser stays the authority on what is markup. This changes only what becomes of what it
 * rejects: a text node carrying the source, which serialises escaped and cannot execute. Registered
 * once, beside the link hook, for the same reason.
 */
DOMPurify.addHook('uponSanitizeElement', (node, data) => {
  if (data.allowedTags[data.tagName]) return
  const parent = node.parentNode
  const source = (node as Element).outerHTML
  if (!parent || typeof source !== 'string' || !node.ownerDocument) return
  parent.replaceChild(node.ownerDocument.createTextNode(source), node)
})

/**
 * Render markdown to sanitized HTML with artifact links mapped to in-app routes.
 *
 * Pass `area` when rendering an artifact's own content, so a same-directory link — one ADR citing
 * another by bare filename — resolves. Omitted, such links are left alone rather than guessed at.
 */
export const renderMarkdown = (content: string, area?: ArtifactArea): string => {
  siblingArea = area
  try {
    return DOMPurify.sanitize(marked.parse(content, { async: false }))
  } finally {
    siblingArea = undefined
  }
}

/**
 * An Effect that takes a string and returns sanitized HTML.
 */
export const parseMarkdown = (content: string, area?: ArtifactArea) =>
  Effect.try({
    try: () => renderMarkdown(content, area),
    catch: (error) => new MarkdownError(`Markdown rendering failed: ${String(error)}`),
  })
