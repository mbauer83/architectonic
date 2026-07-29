import { describe, expect, it } from 'vitest'
import { walkWitnessChain, witnessChainProse } from './witnessChainProse'
import type { ConnectionRecord } from './schemas/connections'

const record = (overrides: Partial<ConnectionRecord>): ConnectionRecord => ({
  artifact_id: 'c', source: 'a', target: 'b', conn_type: 'archimate-serving',
  version: '1', status: 'active', path: '', content_text: '', ...overrides,
})

describe('walkWitnessChain', () => {
  it('walks a two-hop chain from the source entity through each connection in order', () => {
    const c1 = record({ artifact_id: 'c1', source: 'A', target: 'X', conn_type: 'archimate-assignment', source_name: 'Actor A', target_name: 'Component X' })
    const c2 = record({ artifact_id: 'c2', source: 'X', target: 'B', conn_type: 'archimate-serving', source_name: 'Component X', target_name: 'Process B' })
    const steps = walkWitnessChain('A', ['c1', 'c2'], new Map([['c1', c1], ['c2', c2]]))
    expect(steps).toEqual([
      { connectionId: 'c1', connectionType: 'archimate-assignment', fromEntityId: 'A', fromEntityName: 'Actor A', toEntityId: 'X', toEntityName: 'Component X' },
      { connectionId: 'c2', connectionType: 'archimate-serving', fromEntityId: 'X', fromEntityName: 'Component X', toEntityId: 'B', toEntityName: 'Process B' },
    ])
  })

  it('follows a reversed hop (target is the current position) correctly', () => {
    const c1 = record({ artifact_id: 'c1', source: 'X', target: 'A', conn_type: 'archimate-assignment', source_name: 'Component X', target_name: 'Actor A' })
    const steps = walkWitnessChain('A', ['c1'], new Map([['c1', c1]]))
    expect(steps).toEqual([
      { connectionId: 'c1', connectionType: 'archimate-assignment', fromEntityId: 'A', fromEntityName: 'Actor A', toEntityId: 'X', toEntityName: 'Component X' },
    ])
  })

  it('stops at the first unresolved connection id rather than guessing', () => {
    const c1 = record({ artifact_id: 'c1', source: 'A', target: 'X' })
    const steps = walkWitnessChain('A', ['c1', 'missing'], new Map([['c1', c1]]))
    expect(steps).toHaveLength(1)
  })

  it('reconstructs the true path when connection ids arrive out of traversal order', () => {
    // Regression: the derivation engine can extend a composed chain from either end as
    // it discovers adjacent connections, so `via_connection_ids` is not guaranteed to
    // arrive in source-to-target order — this exact scramble was observed live against
    // a real derived relationship (NOD -> ... -> PRC, 4 hops).
    const c1 = record({ artifact_id: 'c1', source: 'X1', target: 'X2', conn_type: 'archimate-composition' })
    const c2 = record({ artifact_id: 'c2', source: 'X2', target: 'X3', conn_type: 'archimate-composition' })
    const c3 = record({ artifact_id: 'c3', source: 'A', target: 'X1', conn_type: 'archimate-serving' })
    const c4 = record({ artifact_id: 'c4', source: 'X3', target: 'B', conn_type: 'archimate-association' })
    // Scrambled order, as actually observed: [c1, c2, c3, c4] rather than [c3, c1, c2, c4].
    const connectionById = new Map([['c1', c1], ['c2', c2], ['c3', c3], ['c4', c4]])
    const steps = walkWitnessChain('A', ['c1', 'c2', 'c3', 'c4'], connectionById)
    expect(steps.map((s) => s.connectionId)).toEqual(['c3', 'c1', 'c2', 'c4'])
    expect(steps[0].fromEntityId).toBe('A')
    expect(steps[steps.length - 1].toEntityId).toBe('B')
  })
})

describe('witnessChainProse', () => {
  it('interleaves entity-name segments with connection-type arrows', () => {
    const segments = witnessChainProse([
      { connectionId: 'c1', connectionType: 'archimate-assignment', fromEntityId: 'A', fromEntityName: 'Actor A', toEntityId: 'X', toEntityName: 'Component X' },
      { connectionId: 'c2', connectionType: 'archimate-serving', fromEntityId: 'X', fromEntityName: 'Component X', toEntityId: 'B', toEntityName: 'Process B' },
    ])
    expect(segments).toEqual([
      { text: 'Actor A', entityId: 'A' },
      { text: ' —(assignment)→ ' },
      { text: 'Component X', entityId: 'X' },
      { text: ' —(serving)→ ' },
      { text: 'Process B', entityId: 'B' },
    ])
  })

  it('produces no segments for an empty chain', () => {
    expect(witnessChainProse([])).toEqual([])
  })
})
