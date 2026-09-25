import type { IconRepository } from '../../ports/IconRepository'
import { IconListSchema, ShownIconsSchema } from '../../domain/schemas/icons'
import { WriteResultSchema } from '../../domain/schemas/write-results'
import { encodeIdentitySegment } from '../../domain/identitySegments'
import { buildUrl, deleteNoContent, fetchJson, patchJson, postJson } from './httpTransport'

/** The icon half of the HTTP adapter, over the library's routes. */
export const iconMethods = (): IconRepository => ({
  listIcons: (params) => fetchJson(buildUrl('/icons', params), IconListSchema),
  // An icon's picture never changes under its id, so the address is stable and a browser may keep it.
  iconImageUrl: (iconId) => `${iconUrl(iconId)}/image`,
  previewShownIcons: (body) => postJson(buildUrl('/icons/preview'), body, ShownIconsSchema),
  // The caller decides whether this is a rehearsal: the dialog normalises with a dry run first.
  createIcon: (upload) => postJson(buildUrl('/icons'), upload, WriteResultSchema),
  editIcon: (iconId, edit) => patchJson(iconUrl(iconId), edit, WriteResultSchema),
  replaceIcon: (iconId, body) => postJson(`${iconUrl(iconId)}/replace`, body, WriteResultSchema),
  shareIcon: (diagramId, iconKey, body) => postJson(
    buildUrl(`/diagrams/${encodeIdentitySegment(diagramId)}/icons/${encodeIdentitySegment(iconKey)}/share`),
    body, WriteResultSchema,
  ),
  // `dry_run=false` because a bare delete answers its plan with 200, which reads as success and removes nothing.
  deleteIcon: (iconId) => deleteNoContent(`${iconUrl(iconId)}?dry_run=false`),
})

const iconUrl = (iconId: string): string => buildUrl(`/icons/${encodeIdentitySegment(iconId)}`)
