import { isRecord } from './errors'

/** Typed guards for the SSE sync-event payloads the app shell consumes. */

export type WriteBlockChangedEvent = { blocked: boolean }
export type SyncPullCompletedEvent = { commits_pulled: number }
export type SyncPullFailedEvent = { error: string; auto_unblock_in_seconds: number }
export type SyncBlockedEvent = { reason: string }

export const parseEventData = <T extends Record<string, unknown>>(
  raw: string,
  guard: (value: Record<string, unknown>) => value is T,
): T | null => {
  try {
    const parsed = JSON.parse(raw) as unknown
    if (isRecord(parsed) && guard(parsed)) return parsed
  } catch {
    return null
  }
  return null
}

export const isWriteBlockChangedEvent = (value: Record<string, unknown>): value is WriteBlockChangedEvent =>
  typeof value.blocked === 'boolean'
export const isSyncPullCompletedEvent = (value: Record<string, unknown>): value is SyncPullCompletedEvent =>
  typeof value.commits_pulled === 'number'
export const isSyncPullFailedEvent = (value: Record<string, unknown>): value is SyncPullFailedEvent =>
  typeof value.error === 'string' && typeof value.auto_unblock_in_seconds === 'number'
export const isSyncBlockedEvent = (value: Record<string, unknown>): value is SyncBlockedEvent =>
  typeof value.reason === 'string'
