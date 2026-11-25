import { describe, expect, it } from 'vitest'
import { ALLOWED, NO_ANSWER_YET, permissionOf, type AuthorityView } from '../permissions'
import type { SyncAuthority } from '../schemas/sync-status'

const authority = (
  operations: Record<string, { denied: boolean; code: string | null }>, message: string | null = null,
): SyncAuthority => ({
  block_kind: 'none', blocked_reason: null, blocked_message: message, denied_intents: {}, denied_operations: operations,
})
const view = (answer: SyncAuthority | null, known = true, writesPaused = false): AuthorityView =>
  ({ known, authority: answer, writesPaused })

describe('the permission answer', () => {
  it('allows what the backend answers allowed', () => {
    expect(permissionOf(view(authority({ 'diagram.compose': { denied: false, code: null } })), 'diagram.compose'))
      .toEqual(ALLOWED)
  })

  it('refuses everything before this tab has an answer of its own', () => {
    const open = authority({ 'diagram.compose': { denied: false, code: null } })
    expect(permissionOf(view(open, false), 'diagram.compose')).toEqual({ allowed: false, reason: NO_ANSWER_YET })
    expect(permissionOf(view(null), 'diagram.compose')).toEqual({ allowed: false, reason: NO_ANSWER_YET })
  })

  it('refuses an operation the backend did not answer for, rather than allowing it', () => {
    expect(permissionOf(view(authority({})), 'diagram.compose').allowed).toBe(false)
  })

  it('refuses while a sync the event stream announced is in progress', () => {
    const open = authority({ 'diagram.compose': { denied: false, code: null } })
    expect(permissionOf(view(open, true, true), 'diagram.compose')).toMatchObject({ allowed: false })
  })

  it('says each denial in words, the role refusal as the sketch words it', () => {
    const reason = (code: string, message: string | null = null) => {
      const answer = permissionOf(view(authority({ op: { denied: true, code } }, message)), 'op')
      return answer.allowed ? null : answer.reason
    }
    expect(reason('not_permitted')).toBe('Not permitted for your role')
    expect(reason('read_only')).toBe('The workspace is read-only')
    expect(reason('admin_mode_required')).toContain('admin mode')
    expect(reason('sync_health', 'The remote cannot be reached')).toBe('The remote cannot be reached')
    expect(reason('something_new')).toBe('Refused by the backend (something_new)')
  })
})
