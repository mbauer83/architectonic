const ROOT_MARKERS = ['documents', 'model', 'diagram-catalog']

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
