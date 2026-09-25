import type { IconRepository } from '../../ports/IconRepository'
import { IconListSchema, ShownIconsSchema } from '../../domain/schemas/icons'
import { WriteResultSchema } from '../../domain/schemas/write-results'
import { encodeIdentitySegment } from '../../domain/identitySegments'
import { buildUrl, fetchJson, postJson } from './httpTransport'

/** The icon half of the HTTP adapter: four methods over the library's routes. */
export const iconMethods = (): IconRepository => ({
  listIcons: (params) => fetchJson(buildUrl('/icons', params), IconListSchema),
  // An icon's picture never changes under its id, so the address is stable and a browser may keep it.
  iconImageUrl: (iconId) => buildUrl(`/icons/${encodeIdentitySegment(iconId)}/image`),
  previewShownIcons: (body) => postJson(buildUrl('/icons/preview'), body, ShownIconsSchema),
  // The caller decides whether this is a rehearsal: the dialog normalises with a dry run first.
  createIcon: (upload) => postJson(buildUrl('/icons'), upload, WriteResultSchema),
})
