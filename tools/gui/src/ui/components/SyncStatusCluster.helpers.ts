import type { EnterpriseSyncStatus, SyncAuthority } from '../../domain'

/**
 * Status & action reducer for the workflow cluster.
 *
 * An action renders as available exactly when its intent is not denied for its
 * target AND the lifecycle row offers it; `behind` is an orthogonal warning
 * overlay applied AFTER action selection — never silently "up to date". A dirty
 * working tree is lifecycle state, never an authority block, so Save stays
 * available to resolve it. With authority unknown (no successful authority
 * response yet) everything is fail-closed.
 */

export type ClusterAction =
  | 'engagement_save'
  | 'enterprise_save'
  | 'enterprise_submit'
  | 'enterprise_discard_local'
  | 'enterprise_discard_pending'
  | 'promote'

export type ClusterTone = 'ok' | 'info' | 'warn' | 'error' | 'muted'

export interface ClusterModel {
  presentation: string
  tone: ClusterTone
  actions: ClusterAction[]
  behindWarning: string | null
  engagementSaveAvailable: boolean
}

export interface ClusterInput {
  authorityKnown: boolean
  authority: SyncAuthority | null
  enterprise: EnterpriseSyncStatus | null
  engagementDirty: boolean
}

const _INTENT_FOR_ACTION: Record<ClusterAction, string> = {
  engagement_save: 'engagement_authoring',
  enterprise_save: 'enterprise_save',
  enterprise_submit: 'enterprise_submit',
  enterprise_discard_local: 'enterprise_discard_local',
  enterprise_discard_pending: 'enterprise_discard_pending',
  promote: 'promotion',
}

const _allowed = (authority: SyncAuthority | null, action: ClusterAction): boolean => {
  const decision = authority?.denied_intents[_INTENT_FOR_ACTION[action]]
  return decision !== undefined && !decision.denied
}

const _lifecycleRow = (enterprise: EnterpriseSyncStatus): { presentation: string; tone: ClusterTone; offered: ClusterAction[] } => {
  const dirty = enterprise.has_uncommitted_changes
  const ahead = enterprise.commits_ahead ?? null
  switch (enterprise.status) {
    case 'synced':
      return dirty
        ? { presentation: 'Unsaved enterprise changes', tone: 'warn', offered: ['enterprise_save'] }
        : { presentation: 'Enterprise up to date — promote engagement work to publish it', tone: 'ok', offered: ['promote'] }
    case 'accumulating':
      if (dirty) return { presentation: 'Changes in progress — unsaved', tone: 'warn', offered: ['enterprise_save'] }
      if (ahead === 0) return { presentation: 'Empty working branch', tone: 'muted', offered: ['enterprise_discard_local'] }
      return { presentation: 'Ready to submit', tone: 'info', offered: ['enterprise_submit', 'enterprise_discard_local'] }
    case 'pending':
      return dirty
        ? {
            presentation: 'Manual recovery needed — the pending branch has unsaved edits; resolve them in the repository',
            tone: 'error',
            offered: [],
          }
        : { presentation: 'Awaiting review', tone: 'info', offered: ['enterprise_discard_pending'] }
  }
}

export const reduceCluster = (input: ClusterInput): ClusterModel => {
  const { authorityKnown, authority, enterprise, engagementDirty } = input

  const engagementSaveAvailable =
    authorityKnown && engagementDirty && _allowed(authority, 'engagement_save')

  if (!authorityKnown || authority === null) {
    return {
      presentation: 'Checking repository status…',
      tone: 'muted',
      actions: [],
      behindWarning: null,
      engagementSaveAvailable: false,
    }
  }

  if (enterprise === null) {
    return {
      presentation: 'Enterprise not configured',
      tone: 'muted',
      actions: [],
      behindWarning: null,
      engagementSaveAvailable,
    }
  }

  const behindWarning =
    (enterprise.commits_behind ?? 0) > 0
      ? `${enterprise.commits_behind} commit(s) behind the enterprise main branch`
      : null

  if (authority.block_kind === 'read_only' || authority.block_kind === 'sync_in_progress') {
    const presentation =
      authority.block_kind === 'read_only'
        ? 'Read-only mode — repository changes are disabled'
        : 'Sync in progress — changes are paused'
    return { presentation, tone: 'warn', actions: [], behindWarning, engagementSaveAvailable: false }
  }

  const row = _lifecycleRow(enterprise)
  const actions = row.offered.filter((action) => _allowed(authority, action))

  if (authority.block_kind === 'sync_health' && enterprise.health !== null) {
    return {
      presentation: `${enterprise.health.message || enterprise.health.reason} — ${row.presentation}`,
      tone: 'error',
      actions,
      behindWarning,
      engagementSaveAvailable,
    }
  }

  return { presentation: row.presentation, tone: row.tone, actions, behindWarning, engagementSaveAvailable }
}
