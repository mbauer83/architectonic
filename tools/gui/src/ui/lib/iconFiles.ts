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

const ATTRIBUTION_KEY = 'arch.icons.lastAttribution'

/** The attribution last given in this session, so adding a vendor's set asks for it once. */
export const rememberedAttribution = (): string => {
  try { return sessionStorage.getItem(ATTRIBUTION_KEY) ?? '' } catch { return '' }
}

export const rememberAttribution = (attribution: string): void => {
  try { sessionStorage.setItem(ATTRIBUTION_KEY, attribution) } catch { /* a private window keeps none */ }
}

/** `azure_kubernetes-service.png` → `azure kubernetes service`. */
export const iconNameFromFile = (fileName: string): string =>
  fileName.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ').trim() || 'Icon'

const base64Of = (file: File): Promise<string> => new Promise((resolve, reject) => {
  const reader = new FileReader()
  // `readAsDataURL` answers a string; the type also admits the ArrayBuffer other reads give.
  reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result.split(',', 2)[1] ?? '' : '')
  reader.onerror = () => reject(reader.error ?? new Error(`${file.name} could not be read`))
  reader.readAsDataURL(file)
})

export const iconUploadFromFile = async (file: File): Promise<IconUploadForDiagram | { refused: string }> => {
  const format = FORMATS[file.type]
  if (!format) return { refused: 'Choose an SVG, PNG, JPEG or WebP file' }
  return { name: iconNameFromFile(file.name), content_base64: await base64Of(file), source_format: format }
}
