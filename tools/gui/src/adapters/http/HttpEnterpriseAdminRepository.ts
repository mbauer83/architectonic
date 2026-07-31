import type { EnterpriseAdminRepository } from '../../ports/EnterpriseAdminRepository'
import { WriteResultSchema } from '../../domain/schemas/write-results'
import { encodeIdentitySegment } from '../../ui/router/artifactRoutes'
import { buildUrl, deleteNoContent, deleteReq, patchJson, postJson } from './httpTransport'

/**
 * The enterprise-admin half of the HTTP adapter.
 *
 * Split out because it is a separate authority — every route here targets the enterprise repository
 * and is refused unless the backend runs in admin mode — and because the composed adapter had grown
 * past the file-size limit. `buildUrl`'s third argument is what selects the `/admin/api` prefix.
 */
export const enterpriseAdminMethods = (): EnterpriseAdminRepository => ({
  adminCreateEntity: (body) =>
    postJson(buildUrl('/entities', undefined, true), body, WriteResultSchema),
  adminEditEntity: (id, body) =>
    patchJson(buildUrl(`/entities/${encodeIdentitySegment(id)}`, undefined, true), body, WriteResultSchema),
  previewAdminDeleteEntity: (id) =>
    deleteReq(
      buildUrl(`/entities/${encodeIdentitySegment(id)}`, { dry_run: true }, true), WriteResultSchema,
    ),
  adminDeleteEntity: (id) =>
    deleteNoContent(buildUrl(`/entities/${encodeIdentitySegment(id)}`, { dry_run: false }, true)),
  adminAddConnection: (body) =>
    postJson(buildUrl('/connections', undefined, true), body, WriteResultSchema),
  previewAdminRemoveConnection: (connectionId) =>
    deleteReq(
      buildUrl(`/connections/${encodeIdentitySegment(connectionId)}`, { dry_run: true }, true),
      WriteResultSchema,
    ),
  adminRemoveConnection: (connectionId) =>
    deleteNoContent(
      buildUrl(`/connections/${encodeIdentitySegment(connectionId)}`, { dry_run: false }, true),
    ),
  previewAdminDeleteDiagram: (id) =>
    deleteReq(
      buildUrl(`/diagrams/${encodeIdentitySegment(id)}`, { dry_run: true }, true), WriteResultSchema,
    ),
  adminDeleteDiagram: (id) =>
    deleteNoContent(buildUrl(`/diagrams/${encodeIdentitySegment(id)}`, { dry_run: false }, true)),
})
