import type { IconUploadForDiagram } from './diagramIcons'

/**
 * A chosen image file as an icon upload: its content base64-encoded, its format from its media type,
 * and a name made from its file name. The server normalises and checks it; this refuses only a file
 * that is no image the product reads.
 */
const FORMATS: Readonly<Record<string, IconUploadForDiagram['source_format']>> = {
  'image/svg+xml': 'svg', 'image/png': 'png', 'image/jpeg': 'jpeg', 'image/webp': 'webp',
}

export const ICON_FILE_TYPES = Object.keys(FORMATS).join(',')

/** `azure_kubernetes-service.png` → `azure kubernetes service`. */
export const iconNameFromFile = (fileName: string): string =>
  fileName.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ').trim() || 'Icon'

const base64Of = (file: File): Promise<string> => new Promise((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => resolve(String(reader.result).split(',', 2)[1] ?? '')
  reader.onerror = () => reject(reader.error)
  reader.readAsDataURL(file)
})

export const iconUploadFromFile = async (file: File): Promise<IconUploadForDiagram | { refused: string }> => {
  const format = FORMATS[file.type]
  if (!format) return { refused: 'Choose an SVG, PNG, JPEG or WebP file' }
  return { name: iconNameFromFile(file.name), content_base64: await base64Of(file), source_format: format }
}
