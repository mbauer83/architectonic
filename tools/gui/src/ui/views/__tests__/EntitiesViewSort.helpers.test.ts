import { describe, expect, it } from 'vitest'
import { SERVER_SORT_KEYS, isServerSortKey, sortEntityRows } from '../EntitiesView.helpers'
import type { EntitySummary } from '../../../domain'

const row = (overrides: Partial<EntitySummary>): EntitySummary => ({
  artifact_id: 'REQ@1.a.a',
  artifact_type: 'requirement',
  name: 'A',
  version: '0.1.0',
  status: 'draft',
  domain: 'motivation',
  subdomain: 'requirement',
  path: '/x.md',
  specializations: [],
  is_global: false,
  ...overrides,
})

describe('isServerSortKey', () => {
  it('claims every native record field the backend can order by', () => {
    expect(SERVER_SORT_KEYS).toEqual(['name', 'artifact_type', 'status', 'domain', 'last_updated'])
    for (const key of SERVER_SORT_KEYS) expect(isServerSortKey(key)).toBe(true)
  })

  it('disclaims the connection counts, which only exist for the loaded page', () => {
    for (const key of ['in', 'sym', 'out', 'total', null]) expect(isServerSortKey(key)).toBe(false)
  })
})

describe('sortEntityRows', () => {
  const items = [
    row({ artifact_id: 'a', artifact_type: 'goal', conn_in: 3, conn_sym: 0, conn_out: 1 }),
    row({ artifact_id: 'b', artifact_type: 'driver', conn_in: 1, conn_sym: 2, conn_out: 5 }),
  ]

  it('null key preserves server order in a fresh copy', () => {
    const sorted = sortEntityRows(items, null, 1)
    expect(sorted.map((r) => r.artifact_id)).toEqual(['a', 'b'])
    expect(sorted).not.toBe(items)
  })

  it('sorts by connection columns in both directions', () => {
    expect(sortEntityRows(items, 'in', -1).map((r) => r.artifact_id)).toEqual(['a', 'b'])
    expect(sortEntityRows(items, 'in', 1).map((r) => r.artifact_id)).toEqual(['b', 'a'])
    expect(sortEntityRows(items, 'total', 1).map((r) => r.artifact_id)).toEqual(['a', 'b'])
    expect(sortEntityRows(items, 'out', -1).map((r) => r.artifact_id)).toEqual(['b', 'a'])
  })

  it('leaves a server-resolved order alone — re-sorting the page would undo it', () => {
    // The server returned these ordered by type descending; the client must not reorder them.
    const serverOrdered = [items[0], items[1]]
    expect(sortEntityRows(serverOrdered, 'artifact_type', 1).map((r) => r.artifact_id)).toEqual(['a', 'b'])
    expect(sortEntityRows(serverOrdered, 'last_updated', -1).map((r) => r.artifact_id)).toEqual(['a', 'b'])
  })
})
