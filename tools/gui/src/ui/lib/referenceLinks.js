const ROOT_MARKERS = ['documents', 'model', 'diagram-catalog']
const ARTIFACT_FILE_RE = /^([A-Z][A-Z0-9]*@\d+\.[a-z0-9]+\.[^./?#]+)\.(md|puml)$/i

export const toRepoRelativePath = (value) => {
  const normalized = String(value ?? '').replace(/\\/g, '/')
  if (!normalized) return ''
  const parts = normalized.split('/').filter(Boolean)
  const markerIndex = parts.findIndex((part) => ROOT_MARKERS.includes(part))
  return markerIndex >= 0 ? parts.slice(markerIndex).join('/') : normalized.replace(/^\/+/, '')
}

export const relativePathBetweenArtifacts = (fromPath, toPath) => {
  const fromRel = toRepoRelativePath(fromPath)
  const toRel = toRepoRelativePath(toPath)
  const fromDir = fromRel.split('/').filter(Boolean).slice(0, -1)
  const toParts = toRel.split('/').filter(Boolean)

  let index = 0
  while (index < fromDir.length && index < toParts.length && fromDir[index] === toParts[index]) index += 1

  const up = new Array(fromDir.length - index).fill('..')
  const down = toParts.slice(index)
  return [...up, ...down].join('/') || toParts[toParts.length - 1] || ''
}

export const toSectionAnchor = (section) =>
  String(section ?? '').toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]/g, '')

export const buildReferenceMarkdown = ({ currentPath, targetPath, title, section }) => {
  const href = relativePathBetweenArtifacts(currentPath, targetPath)
  const suffix = section ? `#${toSectionAnchor(section)}` : ''
  const label = section ? `${title} - ${section}` : title
  return `[${label}](${href}${suffix})`
}

export const draftDocumentPath = (docType, subdirectory) => {
  const targetDir = String(subdirectory || docType || 'draft')
    .replace(/\\/g, '/')
    .replace(/^\/+|\/+$/g, '')
  return `documents/${targetDir || 'draft'}/__draft__.md`
}

export const toGuiArtifactHref = (href) => {
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
  const querySuffix = query ? `&${query}` : ''
  if (marker === 'model') return `/entity?id=${artifactId}${querySuffix}${hash}`
  if (marker === 'documents') return `/document?id=${artifactId}${querySuffix}${hash}`
  if (marker === 'diagram-catalog') return `/diagram?id=${artifactId}${querySuffix}${hash}`
  return value
}
