import { Schema } from 'effect'
import type { ModelRepository } from '../../ports/ModelRepository'
import { GroupListSchema, SyncSaveResultSchema, SyncStatusSchema } from '../../domain/schemas'
import { SyncChangesResultSchema } from '../../domain/schemas-changes'
import { encodeIdentitySegment } from '../../domain/identitySegments'
import { buildUrl, deleteReq, fetchJson, patchJson, postJson } from './httpTransport'

/**
 * The workspace half of the HTTP adapter: git synchronisation, and the groups artifacts are filed in.
 *
 * Split out for the reason `HttpEnterpriseAdminRepository` and `HttpViewpointRepository` were — the
 * composed adapter passed the file-size limit — and this is the seam because these are the routes about
 * the *workspace* rather than about the model in it. Nothing here reads or writes an artifact: `/sync/*`
 * moves commits, `/groups/*` moves the folders artifacts live in.
 *
 * A `Record<string, unknown>` return for the group operations is the port's shape, not a shortcut here:
 * the group routes answer an operation report whose fields differ by action, and typing it would mean
 * one schema per action for values no caller reads.
 */

/** What a group operation answers: an action-shaped report, read by nobody field by field. */
const OperationReport = Schema.Record({ key: Schema.String, value: Schema.Unknown })

// A group is addressed by the pair (axis kind, slug); both segments are encoded, because a slug is
// author-chosen text and an axis is a vocabulary term neither of which the URL grammar guarantees.
const groupPath = (kind: string, slug: string, action = ''): string =>
  `/groups/${encodeIdentitySegment(kind)}/${encodeIdentitySegment(slug)}${action}`
const groupUrl = (kind: string, slug: string, action = ''): string =>
  buildUrl(groupPath(kind, slug, action))

type WorkspaceMethods = Pick<
  ModelRepository,
  | 'getSyncStatus' | 'saveEngagementChanges' | 'saveEnterpriseChanges' | 'submitEnterpriseChanges'
  | 'withdrawEnterpriseChanges' | 'getChanges'
  | 'listGroups' | 'createGroup' | 'renameGroup' | 'archiveGroup' | 'unarchiveGroup'
  | 'deleteGroup' | 'updateGroup'
>

export const workspaceMethods = (): WorkspaceMethods => ({
  getSyncStatus: () => fetchJson(buildUrl('/sync/status'), SyncStatusSchema),
  saveEngagementChanges: (body) =>
    postJson(buildUrl('/sync/engagement/save'), { push: true, ...body }, SyncSaveResultSchema),
  saveEnterpriseChanges: (body) =>
    postJson(buildUrl('/sync/enterprise/save'), body, SyncSaveResultSchema),
  submitEnterpriseChanges: () =>
    postJson(buildUrl('/sync/enterprise/submit'), {}, SyncSaveResultSchema),
  // The typed confirmation the route requires is supplied here rather than by the caller: it is a
  // property of *this address*, not a decision the application layer makes twice.
  withdrawEnterpriseChanges: () =>
    postJson(buildUrl('/sync/enterprise/withdraw'), { confirm: true }, SyncSaveResultSchema),
  getChanges: (repo) => fetchJson(buildUrl('/sync/changes', { repo }), SyncChangesResultSchema),

  listGroups: (kind?: string) =>
    fetchJson(buildUrl('/groups', kind !== undefined ? { kind } : undefined), GroupListSchema),
  createGroup: (body) => postJson(buildUrl('/groups'), body, OperationReport),
  // A POST with an action segment, not a PATCH field: a rename re-files every member and changes the
  // resource's own address.
  renameGroup: (kind, slug, body) => postJson(groupUrl(kind, slug, '/rename'), body, OperationReport),
  archiveGroup: (kind, slug, body) => postJson(groupUrl(kind, slug, '/archive'), body, OperationReport),
  unarchiveGroup: (kind, slug) => postJson(groupUrl(kind, slug, '/unarchive'), {}, OperationReport),
  deleteGroup: (kind, slug, confirm) =>
    deleteReq(buildUrl(groupPath(kind, slug), { confirm }), OperationReport),
  updateGroup: (kind, slug, body) => patchJson(groupUrl(kind, slug), body, OperationReport),
})
