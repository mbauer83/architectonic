import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { SyncStatus } from '../../domain'
import { readErrorMessage } from '../lib/errors'
import {
  isSyncBlockedEvent,
  isSyncPullCompletedEvent,
  isSyncPullFailedEvent,
  isWriteBlockChangedEvent,
  parseEventData,
} from '../lib/syncEvents'

type Toast = (message: string, type?: 'info' | 'warn' | 'error', durationMs?: number) => void

const SYNC_STATUS_CACHE_KEY = 'arch.gui.sync-status.cache.v1'
const SYNC_STATUS_LEASE_KEY = 'arch.gui.sync-status.lease.v1'
const SYNC_STATUS_LEASE_MS = 90_000
const SYNC_STATUS_LEASE_RENEW_MS = 30_000
const SYNC_STATUS_RECONCILE_MS = 120_000

type SyncStatusCacheEnvelope = { updatedAt: number; status: SyncStatus }
type SyncStatusLease = { tabId: string; expiresAt: number }

/**
 * Sync/authority coordination for the app shell.
 *
 * FAIL-CLOSED: mutation authority starts UNKNOWN and every mutating control
 * stays disabled until THIS tab's first successful authority response (a
 * cross-tab cached status renders lifecycle info but never enables actions;
 * a failed server-info or status request keeps everything closed). SSE events
 * only trigger re-reads of backend authority — they are never its source.
 */
export function useSyncCoordination(svc: ModelService, addToast: Toast) {
  const adminMode = ref(false)
  const readOnly = ref(false)
  const writeBlocked = ref(false)
  const serverInfoKnown = ref(false)
  const authorityFresh = ref(false)
  const syncStatus = ref<SyncStatus | null>(null)

  let syncStatusRequestInFlight = false
  let queuedSyncStatusRefresh = false
  let syncStatusDebounceTimer: ReturnType<typeof setTimeout> | null = null
  let syncLeaderLeaseTimer: ReturnType<typeof setInterval> | null = null
  let syncLeaderPollTimer: ReturnType<typeof setInterval> | null = null
  const syncLeaderTabId = `tab-${Date.now()}-${Math.random().toString(36).slice(2)}`
  let eventSource: EventSource | null = null

  const authorityKnown = computed(() => authorityFresh.value && serverInfoKnown.value)
  const anyWriteBlocked = computed(
    () => !authorityKnown.value || readOnly.value || writeBlocked.value,
  )
  const authority = computed(() => (authorityFresh.value ? (syncStatus.value?.authority ?? null) : null))
  const engDirty = computed(() => syncStatus.value?.engagement?.has_uncommitted_changes ?? false)
  const entStatus = computed(() => syncStatus.value?.enterprise ?? null)

  const readSyncStatusCache = (): SyncStatusCacheEnvelope | null => {
    try {
      const raw = window.localStorage.getItem(SYNC_STATUS_CACHE_KEY)
      if (!raw) return null
      const parsed = JSON.parse(raw) as Partial<SyncStatusCacheEnvelope>
      if (!parsed || typeof parsed.updatedAt !== 'number' || typeof parsed.status !== 'object') return null
      return { updatedAt: parsed.updatedAt, status: parsed.status }
    } catch {
      return null
    }
  }

  const publishSyncStatusCache = (status: SyncStatus) => {
    try {
      const envelope: SyncStatusCacheEnvelope = { updatedAt: Date.now(), status }
      window.localStorage.setItem(SYNC_STATUS_CACHE_KEY, JSON.stringify(envelope))
    } catch {
      // Ignore localStorage quota/privacy failures; the local tab still updates.
    }
  }

  const readSyncLease = (): SyncStatusLease | null => {
    try {
      const raw = window.localStorage.getItem(SYNC_STATUS_LEASE_KEY)
      if (!raw) return null
      const parsed = JSON.parse(raw) as Partial<SyncStatusLease>
      if (!parsed || typeof parsed.tabId !== 'string' || typeof parsed.expiresAt !== 'number') return null
      return { tabId: parsed.tabId, expiresAt: parsed.expiresAt }
    } catch {
      return null
    }
  }

  const stopSyncLeaderPoll = () => {
    if (syncLeaderPollTimer !== null) {
      clearInterval(syncLeaderPollTimer)
      syncLeaderPollTimer = null
    }
  }

  const startSyncLeaderPoll = () => {
    if (syncLeaderPollTimer !== null) return
    syncLeaderPollTimer = setInterval(() => { loadSyncStatus() }, SYNC_STATUS_RECONCILE_MS)
  }

  const updateSyncLeaderRole = (isLeader: boolean) => {
    if (isLeader) startSyncLeaderPoll()
    else stopSyncLeaderPoll()
  }

  const tryAcquireSyncLease = (): void => {
    const now = Date.now()
    const current = readSyncLease()
    if (current && current.tabId !== syncLeaderTabId && current.expiresAt > now) {
      updateSyncLeaderRole(false)
      return
    }
    try {
      const nextLease: SyncStatusLease = { tabId: syncLeaderTabId, expiresAt: now + SYNC_STATUS_LEASE_MS }
      window.localStorage.setItem(SYNC_STATUS_LEASE_KEY, JSON.stringify(nextLease))
      const confirmed = readSyncLease()
      updateSyncLeaderRole(confirmed?.tabId === syncLeaderTabId)
    } catch {
      updateSyncLeaderRole(true)
    }
  }

  const loadSyncStatus = () => {
    if (syncStatusRequestInFlight) {
      queuedSyncStatusRefresh = true
      return
    }
    syncStatusRequestInFlight = true
    void Effect.runPromise(svc.getSyncStatus())
      .then((status) => {
        syncStatus.value = status
        authorityFresh.value = true
        publishSyncStatusCache(status)
      })
      .catch((error: unknown) => {
        addToast(`Failed to load sync status: ${readErrorMessage(error)}`, 'error')
      })
      .finally(() => {
        syncStatusRequestInFlight = false
        if (queuedSyncStatusRefresh) {
          queuedSyncStatusRefresh = false
          loadSyncStatus()
        }
      })
  }

  const scheduleSyncStatusRefresh = (delayMs = 150) => {
    if (syncStatusDebounceTimer !== null) clearTimeout(syncStatusDebounceTimer)
    syncStatusDebounceTimer = setTimeout(() => {
      syncStatusDebounceTimer = null
      loadSyncStatus()
    }, delayMs)
  }

  const onStorageChanged = (event: StorageEvent) => {
    if (event.key === SYNC_STATUS_CACHE_KEY && event.newValue) {
      // Lifecycle info only — another tab's response never counts as THIS tab's
      // authority (authorityFresh stays as-is).
      const cached = readSyncStatusCache()
      if (cached) syncStatus.value = cached.status
    }
    if (event.key === SYNC_STATUS_LEASE_KEY) {
      const lease = readSyncLease()
      updateSyncLeaderRole(lease?.tabId === syncLeaderTabId)
    }
  }

  onMounted(() => {
    void Effect.runPromise(svc.getServerInfo())
      .then((info) => {
        adminMode.value = info.admin_mode
        readOnly.value = info.read_only
        serverInfoKnown.value = true
      })
      .catch((error: unknown) => {
        // Fail closed: serverInfoKnown stays false, so authority stays unknown.
        addToast(`Failed to load server info: ${readErrorMessage(error)}`, 'error')
      })

    const cachedSyncStatus = readSyncStatusCache()
    if (cachedSyncStatus) syncStatus.value = cachedSyncStatus.status
    loadSyncStatus()
    tryAcquireSyncLease()
    syncLeaderLeaseTimer = setInterval(() => { tryAcquireSyncLease() }, SYNC_STATUS_LEASE_RENEW_MS)
    window.addEventListener('storage', onStorageChanged)

    try {
      eventSource = new EventSource('/api/events')

      eventSource.addEventListener('write_block_changed', (e: MessageEvent<string>) => {
        const data = parseEventData(e.data, isWriteBlockChangedEvent)
        if (!data) {
          addToast('Received malformed write-block event', 'error')
          return
        }
        writeBlocked.value = data.blocked
        addToast(
          data.blocked ? 'Sync in progress — writes paused' : 'Sync complete — writes resumed',
          data.blocked ? 'warn' : 'info',
        )
        scheduleSyncStatusRefresh()
      })
      eventSource.addEventListener('sync_pull_started', () => { addToast('Pulling updates…', 'info') })
      eventSource.addEventListener('sync_pull_completed', (e: MessageEvent<string>) => {
        const data = parseEventData(e.data, isSyncPullCompletedEvent)
        if (!data) {
          addToast('Received malformed sync-complete event', 'error')
          return
        }
        addToast(`Pulled ${data.commits_pulled} commit(s)`, 'info')
        scheduleSyncStatusRefresh()
      })
      eventSource.addEventListener('sync_pull_failed', (e: MessageEvent<string>) => {
        const data = parseEventData(e.data, isSyncPullFailedEvent)
        if (!data) {
          addToast('Received malformed sync-failure event', 'error')
          return
        }
        addToast(`Sync failed: ${data.error}. Writes resume in ${data.auto_unblock_in_seconds}s`, 'error', 7000)
      })
      eventSource.addEventListener('sync_blocked', (e: MessageEvent<string>) => {
        const data = parseEventData(e.data, isSyncBlockedEvent)
        if (!data) {
          addToast('Received malformed sync-blocked event', 'error')
          return
        }
        addToast(`Sync blocked: ${data.reason}`, 'error', 10000)
        scheduleSyncStatusRefresh()
      })

      const onSyncEvent = (label: string) => () => { addToast(label, 'info'); scheduleSyncStatusRefresh() }
      eventSource.addEventListener('sync_engagement_saved', onSyncEvent('Engagement changes saved'))
      eventSource.addEventListener('sync_enterprise_saved', onSyncEvent('Enterprise changes saved'))
      eventSource.addEventListener('sync_enterprise_submitted', onSyncEvent('Enterprise submission ready'))
      eventSource.addEventListener('sync_enterprise_withdrawn', onSyncEvent('Enterprise submission withdrawn'))
      eventSource.addEventListener('sync_status_changed', () => { scheduleSyncStatusRefresh() })
      eventSource.addEventListener('sync_repository_updated', () => { scheduleSyncStatusRefresh() })
      eventSource.addEventListener('artifact_write_completed', () => { scheduleSyncStatusRefresh() })
    } catch (err) {
      console.error('Failed to connect to event stream:', err)
    }
  })

  onUnmounted(() => {
    if (eventSource) eventSource.close()
    if (syncStatusDebounceTimer !== null) clearTimeout(syncStatusDebounceTimer)
    if (syncLeaderLeaseTimer !== null) clearInterval(syncLeaderLeaseTimer)
    stopSyncLeaderPoll()
    window.removeEventListener('storage', onStorageChanged)
  })

  return {
    adminMode,
    readOnly,
    anyWriteBlocked,
    authorityKnown,
    authority,
    syncStatus,
    engDirty,
    entStatus,
    loadSyncStatus,
  }
}
