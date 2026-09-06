import { Effect } from 'effect'
import {
  ChangeDiscardedSchema,
  ChangeListSchema,
  DocumentDetailSchema,
  DocumentListSchema,
  DocumentTypesSchema,
  WriteResultSchema,
} from '../../domain/schemas'
import type { ChangeRepository } from '../../ports/ChangeRepository'
import type { DocumentRepository } from '../../ports/DocumentRepository'
import {
  buildUrl, deleteNoContent, deleteReq, fetchJson, fetchJsonNotFound, patchJson, postJson,
} from './httpTransport'
import { encodeIdentitySegment } from '../../domain/identitySegments'

/**
 * The document surface and the local-change surface, over HTTP.
 *
 * Together because a change is an edit to a document, an entity or a diagram that this
 * repository does not own — and because the composite adapter had reached the source-length
 * policy's ceiling, which is the signal to divide along a seam rather than to keep adding.
 */
export const documentAndChangeMethods = (): DocumentRepository & ChangeRepository => ({
  // The port speaks in document types, not envelopes: the create form wants the list and has no use
  // for the wrapper, so unwrapping here keeps the envelope an HTTP detail.
  listDocumentTypes: () =>
    fetchJson(buildUrl('/document-types'), DocumentTypesSchema).pipe(
      Effect.map((envelope) => [...envelope.document_types] as import('../../domain').DocumentType[]),
    ),

  listDocuments: (
    params: {
      doc_type?: string; status?: string; limit?: number; offset?: number; group?: string; scope?: string;
    } = {},
  ) =>
    fetchJson(buildUrl('/documents', {
      doc_type: params.doc_type, status: params.status,
      limit: params.limit, offset: params.offset, group: params.group, scope: params.scope,
    }), DocumentListSchema),

  getDocument: (id) =>
    fetchJsonNotFound(buildUrl(`/documents/${encodeIdentitySegment(id)}`), DocumentDetailSchema, id),

  createDocument: (body) =>
    postJson(buildUrl('/documents'), body, WriteResultSchema),

  editDocument: (id, body) =>
    patchJson(buildUrl(`/documents/${encodeIdentitySegment(id)}`), body, WriteResultSchema),

  // `dry_run: false` explicitly, as every other delete in this adapter does. It relied on the
  // route's default, and that default was the odd one out on the whole write surface — so the two
  // mistakes cancelled, and neither was visible from either side alone.
  deleteDocument: (id) =>
    deleteNoContent(buildUrl(`/documents/${encodeIdentitySegment(id)}`, { dry_run: false })),

  listChanges: () => fetchJson(buildUrl('/changes', {}), ChangeListSchema),

  // A DELETE that answers rather than 204ing: the record is kept in a terminal state, so the reply
  // says what happened to it instead of implying it is gone.
  discardChange: (id) =>
    deleteReq(buildUrl(`/changes/${encodeIdentitySegment(id)}`, {}), ChangeDiscardedSchema),
})
