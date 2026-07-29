import { describe, it, expect } from 'vitest'
import type { EnterpriseSyncStatus, SyncAuthority } from '../../../domain'
import { reduceCluster, type ClusterInput } from '../SyncStatusCluster.helpers'

const openAuthority = (denied: string[] = []): SyncAuthority => ({
  block_kind: 'none',
  blocked_reason: null,
  blocked_message: null,
  denied_intents: Object.fromEntries(
    [
      'engagement_authoring',
      'enterprise_admin_authoring',
      'promotion',
      'enterprise_save',
      'enterprise_submit',
      'enterprise_discard_local',
      'enterprise_discard_pending',
      'maintenance',
    ].map((intent) => [intent, { denied: denied.includes(intent), code: denied.includes(intent) ? 'x' : null }]),
  ),
})

const enterprise = (overrides: Partial<EnterpriseSyncStatus>): EnterpriseSyncStatus => ({
  status: 'synced',
  label: 'Up to date',
  branch: null,
  branch_tip: null,
  pushed_at: null,
  commits_behind: 0,
  has_uncommitted_changes: false,
  health: null,
  ...overrides,
})

const input = (overrides: Partial<ClusterInput>): ClusterInput => ({
  authorityKnown: true,
  authority: openAuthority(),
  enterprise: enterprise({}),
  engagementDirty: false,
  ...overrides,
})

describe('fail-closed rows', () => {
  it('authority unknown offers nothing', () => {
    const model = reduceCluster(input({ authorityKnown: false, authority: null }))
    expect(model.actions).toEqual([])
    expect(model.engagementSaveAvailable).toBe(false)
    expect(model.presentation).toContain('Checking')
  })

  it('enterprise not configured', () => {
    const model = reduceCluster(input({ enterprise: null }))
    expect(model.presentation).toBe('Enterprise not configured')
    expect(model.actions).toEqual([])
  })

  it('read-only / transient gate block offers nothing until unblock', () => {
    for (const kind of ['read_only', 'sync_in_progress'] as const) {
      const authority = { ...openAuthority(), block_kind: kind }
      const model = reduceCluster(input({ authority, engagementDirty: true }))
      expect(model.actions).toEqual([])
      expect(model.engagementSaveAvailable).toBe(false)
    }
  })
})

describe('§-free lifecycle rows', () => {
  it('synced clean offers Promote with the workflow hint', () => {
    const model = reduceCluster(input({}))
    expect(model.actions).toEqual(['promote'])
    expect(model.presentation).toContain('up to date')
  })

  it('synced dirty offers Save', () => {
    const model = reduceCluster(input({ enterprise: enterprise({ has_uncommitted_changes: true }) }))
    expect(model.presentation).toBe('Unsaved enterprise changes')
    expect(model.actions).toEqual(['enterprise_save'])
  })

  it('accumulating clean ahead=0 offers Discard of the empty local branch', () => {
    const model = reduceCluster(
      input({ enterprise: enterprise({ status: 'accumulating', commits_ahead: 0 }) }),
    )
    expect(model.presentation).toBe('Empty working branch')
    expect(model.actions).toEqual(['enterprise_discard_local'])
  })

  it('accumulating dirty offers Save', () => {
    const model = reduceCluster(
      input({ enterprise: enterprise({ status: 'accumulating', has_uncommitted_changes: true, commits_ahead: 1 }) }),
    )
    expect(model.presentation).toBe('Changes in progress — unsaved')
    expect(model.actions).toEqual(['enterprise_save'])
  })

  it('accumulating clean ahead>0 offers Submit and local Discard', () => {
    const model = reduceCluster(
      input({ enterprise: enterprise({ status: 'accumulating', commits_ahead: 2 }) }),
    )
    expect(model.presentation).toBe('Ready to submit')
    expect(model.actions).toEqual(['enterprise_submit', 'enterprise_discard_local'])
  })

  it('pending clean offers the remote-touching Discard', () => {
    const model = reduceCluster(input({ enterprise: enterprise({ status: 'pending' }) }))
    expect(model.presentation).toBe('Awaiting review')
    expect(model.actions).toEqual(['enterprise_discard_pending'])
  })

  it('pending dirty needs manual recovery and offers nothing', () => {
    const model = reduceCluster(
      input({ enterprise: enterprise({ status: 'pending', has_uncommitted_changes: true }) }),
    )
    expect(model.presentation).toContain('Manual recovery needed')
    expect(model.actions).toEqual([])
  })
})

describe('precedence and overlays', () => {
  it('dirty wins presentation over behind — behind stays an overlay', () => {
    const model = reduceCluster(
      input({
        enterprise: enterprise({ status: 'accumulating', has_uncommitted_changes: true, commits_behind: 3, commits_ahead: 1 }),
      }),
    )
    expect(model.presentation).toBe('Changes in progress — unsaved')
    expect(model.behindWarning).toContain('3 commit(s) behind')
  })

  it('behind never reads as silently up to date', () => {
    const model = reduceCluster(input({ enterprise: enterprise({ commits_behind: 2 }) }))
    expect(model.behindWarning).toContain('2 commit(s) behind')
  })

  it('health block shows the reason plus the lifecycle state and keeps allowed actions', () => {
    const authority: SyncAuthority = {
      ...openAuthority(['promotion', 'enterprise_submit', 'enterprise_discard_pending']),
      block_kind: 'sync_health',
      blocked_reason: 'fetch_failed',
      blocked_message: 'origin unreachable',
    }
    const model = reduceCluster(
      input({
        authority,
        enterprise: enterprise({
          status: 'synced',
          has_uncommitted_changes: true,
          health: { reason: 'fetch_failed', message: 'origin unreachable', observed_at: '2026-07-18T00:00:00Z' },
        }),
      }),
    )
    expect(model.presentation).toContain('origin unreachable')
    expect(model.actions).toEqual(['enterprise_save'])
  })

  it('health block denying submit removes it from an otherwise ready row', () => {
    const authority: SyncAuthority = {
      ...openAuthority(['promotion', 'enterprise_submit', 'enterprise_discard_pending']),
      block_kind: 'sync_health',
      blocked_reason: 'fetch_failed',
      blocked_message: 'origin unreachable',
    }
    const model = reduceCluster(
      input({
        authority,
        enterprise: enterprise({
          status: 'accumulating',
          commits_ahead: 2,
          health: { reason: 'fetch_failed', message: 'origin unreachable', observed_at: '2026-07-18T00:00:00Z' },
        }),
      }),
    )
    expect(model.actions).toEqual(['enterprise_discard_local'])
  })

  it('engagement save follows dirty state and engagement authority', () => {
    expect(reduceCluster(input({ engagementDirty: true })).engagementSaveAvailable).toBe(true)
    expect(reduceCluster(input({ engagementDirty: false })).engagementSaveAvailable).toBe(false)
    expect(
      reduceCluster(input({ engagementDirty: true, authority: openAuthority(['engagement_authoring']) }))
        .engagementSaveAvailable,
    ).toBe(false)
  })
})
