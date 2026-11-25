/**
 * Whether a named operation may be done now, and why not: the one permission answer the GUI disables
 * a control by and says the reason of.
 *
 * The decision is the backend's. It projects one for every operation of its operation catalog
 * (`denied_operations` in the sync status, `src/infrastructure/operation_catalog.py`), composed by the
 * same function its writes are authorized with; this only reads it, and words the denial. Nothing here
 * decides from what a control is or where it sits. It fails closed: with no answer yet, or for a name
 * the backend did not answer for, an operation is refused.
 */
import type { SyncAuthority } from './schemas/sync-status'

export type Permission =
  | { readonly allowed: true }
  | { readonly allowed: false; readonly reason: string }

export const ALLOWED: Permission = { allowed: true }

const refused = (reason: string): Permission => ({ allowed: false, reason })

/** What the page knows of the backend's authority: its last answer, and a sync announced since. */
export interface AuthorityView {
  /** Whether this tab has had an answer of its own (`useSyncCoordination`). */
  readonly known: boolean
  readonly authority: SyncAuthority | null
  /** A sync the event stream announced, which the next answer will state too. */
  readonly writesPaused: boolean
}

export const NO_ANSWER_YET = 'Waiting for the backend to say what may be changed'
const SYNC_IN_PROGRESS = 'A sync is in progress; changes can be made again when it completes'

/** A denial code in words. `not_permitted` is the answer a policy over who is asking will give. */
const REASONS: Readonly<Record<string, string>> = {
  read_only: 'The workspace is read-only',
  sync_in_progress: SYNC_IN_PROGRESS,
  admin_mode_required: 'Only a backend in admin mode writes to the enterprise repository',
  not_configured: 'The repository it writes to is not configured',
  not_permitted: 'Not permitted for your role',
  enterprise_target_forbidden: 'This workspace does not write to the enterprise repository directly',
  target_not_engagement_root: 'It would write outside the engagement repository',
  target_not_enterprise_root: 'It would write outside the enterprise repository',
}

const reasonFor = (code: string | null, authority: SyncAuthority): string =>
  (code === 'sync_health' ? authority.blocked_message : null)
  ?? REASONS[code ?? ''] ?? `Refused by the backend${code ? ` (${code})` : ''}`

/** Whether *operation* may be done now, as *view* answers it. */
export const permissionOf = (view: AuthorityView, operation: string): Permission => {
  const { authority } = view
  if (!view.known || authority === null) return refused(NO_ANSWER_YET)
  if (view.writesPaused) return refused(SYNC_IN_PROGRESS)
  const answered = authority.denied_operations
  const decision = Object.hasOwn(answered, operation) ? answered[operation] : undefined
  if (decision === undefined)return refused(`“${operation}” is not an operation the backend answers for`)
  return decision.denied ? refused(reasonFor(decision.code, authority)) : ALLOWED
}
