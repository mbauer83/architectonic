import { describe, expect, it } from 'vitest'
import { Effect } from 'effect'
import { useWitnessChain, type WitnessChainReadAccess } from './useWitnessChain'
import type { ConnectionRecord, ConnectionList } from '../../domain/schemas/connections'

const record = (overrides: Partial<ConnectionRecord>): ConnectionRecord => ({
  artifact_id: 'c', source: 'a', target: 'b', conn_type: 'archimate-serving',
  version: '1', status: 'active', path: '', content_text: '', ...overrides,
})

/** A minimal `getConnections` stub: every entity's full adjacency, keyed by entity id —
 * the composable's own frontier search (mirroring how a real store answers per-entity
 * queries) has to discover the chain by walking outward from both known endpoints. */
const fakeReadAccess = (adjacency: Record<string, ConnectionList>): WitnessChainReadAccess => ({
  getConnections: (entityId: string) => Effect.succeed(adjacency[entityId] ?? []),
})

describe('useWitnessChain', () => {
  it('resolves a multi-hop chain by searching outward from both known endpoints', async () => {
    const c1 = record({ artifact_id: 'c1', source: 'A', target: 'X', conn_type: 'archimate-assignment', source_name: 'Actor A', target_name: 'Component X' })
    const c2 = record({ artifact_id: 'c2', source: 'X', target: 'B', conn_type: 'archimate-serving', source_name: 'Component X', target_name: 'Process B' })
    const svc = fakeReadAccess({ A: [c1], X: [c1, c2], B: [c2] })
    const chain = useWitnessChain(svc)

    await chain.load('A', 'B', ['c1', 'c2'])

    expect(chain.loading.value).toBe(false)
    expect(chain.broken.value).toBe(false)
    expect(chain.segments.value).toEqual([
      { text: 'Actor A', entityId: 'A' },
      { text: ' —(assignment)→ ' },
      { text: 'Component X', entityId: 'X' },
      { text: ' —(serving)→ ' },
      { text: 'Process B', entityId: 'B' },
    ])
  })

  it('flags a broken chain when a connection id can never be found from either endpoint', async () => {
    const c1 = record({ artifact_id: 'c1', source: 'A', target: 'X' })
    const svc = fakeReadAccess({ A: [c1], X: [c1], B: [] })
    const chain = useWitnessChain(svc)

    await chain.load('A', 'B', ['c1', 'missing'])

    expect(chain.broken.value).toBe(true)
    expect(chain.segments.value.length).toBeGreaterThan(0)
  })

  it('sets loading true synchronously when load starts, and false once resolved', () => {
    const svc = fakeReadAccess({ A: [], B: [] })
    const chain = useWitnessChain(svc)

    const pending = chain.load('A', 'B', [])
    expect(chain.loading.value).toBe(true)

    return pending.then(() => {
      expect(chain.loading.value).toBe(false)
    })
  })

  it('clear resets segments/broken/loading to their empty defaults', async () => {
    const c1 = record({ artifact_id: 'c1', source: 'A', target: 'B' })
    const svc = fakeReadAccess({ A: [c1], B: [c1] })
    const chain = useWitnessChain(svc)
    await chain.load('A', 'B', ['c1'])
    expect(chain.segments.value.length).toBeGreaterThan(0)

    chain.clear()

    expect(chain.segments.value).toEqual([])
    expect(chain.broken.value).toBe(false)
    expect(chain.loading.value).toBe(false)
  })
})
