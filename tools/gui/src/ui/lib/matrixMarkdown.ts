import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { diagramDetailRoute, documentDetailRoute, entityDetailRoute } from '../router/artifactRoutes'

const HREF_ATTR_RE = /href="([^"]+)"/g
const ROOT_MARKERS = ['documents', 'model', 'diagram-catalog']
/** Repository area, as the matrix body's own hrefs spell it, → that area's detail route. */
const DETAIL_ROUTE_BY_MARKER: Record<string, (id: string) => string> = {
  model: entityDetailRoute,
  documents: documentDetailRoute,
  'diagram-catalog': diagramDetailRoute,
}

const ARTIFACT_FILE_RE = /^([A-Z][A-Z0-9]*@\d+\.[^.]+\.[^./?#]+)\.(md|puml)$/i

const toRepoRelativePath = (value: string): string => {
  const normalized = String(value ?? '').replace(/\\/g, '/')
  if (!normalized) return ''
  const parts = normalized.split('/').filter(Boolean)
  const markerIndex = parts.findIndex((part) => ROOT_MARKERS.includes(part))
  return markerIndex >= 0 ? parts.slice(markerIndex).join('/') : normalized.replace(/^\/+/, '')
}

export const toGuiArtifactHref = (href: string): string => {
  const value = String(href ?? '').trim()
  if (!value || value.startsWith('#')) return value
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(value) || value.startsWith('//')) return value

  const hashIndex = value.indexOf('#')
  const hash = hashIndex >= 0 ? value.slice(hashIndex) : ''
  const withoutHash = hashIndex >= 0 ? value.slice(0, hashIndex) : value
  const queryIndex = withoutHash.indexOf('?')
  const query = queryIndex >= 0 ? withoutHash.slice(queryIndex + 1) : ''
  const pathOnly = queryIndex >= 0 ? withoutHash.slice(0, queryIndex) : withoutHash
  const repoRelative = toRepoRelativePath(pathOnly)
  const parts = repoRelative.split('/').filter(Boolean)
  if (!parts.length) return value

  const marker = parts[0]
  const fileName = parts[parts.length - 1] ?? ''
  const match = ARTIFACT_FILE_RE.exec(fileName)
  if (!match) return value

  const artifactId = match[1]
  // Built from the route builders, not spelled here. The `documents` arm used to emit
  // `/document?id=` — a route that has never existed — which is what a second, hand-written copy of
  // the addressing rules produces.
  const detail = DETAIL_ROUTE_BY_MARKER[marker]
  if (detail === undefined) return value
  const querySuffix = query ? `?${query}` : ''
  return `${detail(artifactId)}${querySuffix}${hash}`
}

export const renderMatrixMarkdown = (markdown: string): string => {
  const rawHtml = marked.parse(markdown) as string
  const rewrittenHtml = rawHtml.replace(HREF_ATTR_RE, (_full, href: string) =>
    `href="${toGuiArtifactHref(href)}"`,
  )
  return DOMPurify.sanitize(rewrittenHtml)
}
