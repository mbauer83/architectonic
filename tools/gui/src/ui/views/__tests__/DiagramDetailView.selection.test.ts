/**
 * Tests for T18: node/edge selection state machine in DiagramDetailView.
 *
 * Three testable layers (all pure logic, no browser/SVG needed):
 *  1. buildConnectionAliasMap / resolveConnection — edge interactivity lookup.
 *  2. Selection state machine — toggle, mutual exclusion between node and edge.
 *  3. Derived C4 awareness — entities from context.entities (not diagram_entities)
 *     surface in buildAliasToId and are therefore selectable.
 *
 * SVG click attachment requires a rendered SVG; covered by Playwright (T18 smoke test).
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { buildConnectionAliasMap, resolveConnection, buildAliasToId } from '../DiagramDetailView.helpers'
import type { DiagramConnection, EntitySummary } from '../../../domain'

// ── helpers ──────────────────────────────────────────────────────────────────

const makeConn = (
  sourceAlias: string,
  targetAlias: string,
  id: string,
  connType = 'flow',
): DiagramConnection => ({
  artifact_id: id,
  conn_type: connType,
  source: sourceAlias,
  target: targetAlias,
  source_alias: sourceAlias,
  target_alias: targetAlias,
  source_name: sourceAlias,
  target_name: targetAlias,
  content_text: '',
  version: '0.1.0',
  status: 'active',
  path: '/tmp/x.md',
  edge_label_override: null,
  edge_key: null,
})

const makeEntity = (id: string, alias: string, hostDiagramId?: string): EntitySummary => ({
  artifact_id: id,
  artifact_type: 'application-component',
  name: id,
  version: '0.1.0',
  status: 'active',
  domain: 'application',
  subdomain: '',
  path: '/tmp/x.md',
  is_global: false,
  group: 'uncategorized',
  display_alias: alias,
  host_diagram_id: hostDiagramId,
})

// ── 1. buildConnectionAliasMap / resolveConnection ────────────────────────────

describe('buildConnectionAliasMap', () => {
  it('returns empty maps when connections array is empty', () => {
    const { queue, fallback } = buildConnectionAliasMap([])
    expect(queue.size).toBe(0)
    expect(fallback.size).toBe(0)
  })

  it('skips connections missing source_alias or target_alias', () => {
    const incomplete = [
      { ...makeConn('A', 'B', 'C1'), source_alias: null },
      { ...makeConn('A', 'B', 'C2'), target_alias: '' },
    ] as unknown as DiagramConnection[]
    const { queue, fallback } = buildConnectionAliasMap(incomplete)
    expect(queue.size).toBe(0)
    expect(fallback.size).toBe(0)
  })

  it('stores connection in forward queue key', () => {
    const { queue } = buildConnectionAliasMap([makeConn('A', 'B', 'C1')])
    expect(queue.get('A:B')).toHaveLength(1)
    expect(queue.get('A:B')![0].artifact_id).toBe('C1')
  })

  it('stores first-seen connection in fallback for both directions', () => {
    const { fallback } = buildConnectionAliasMap([makeConn('A', 'B', 'C1')])
    expect(fallback.get('A:B')?.artifact_id).toBe('C1')
    expect(fallback.get('B:A')?.artifact_id).toBe('C1')
  })

  it('does not overwrite existing reverse fallback with a later connection\'s reverse', () => {
    const conns = [makeConn('A', 'B', 'C1'), makeConn('B', 'A', 'C2')]
    const { fallback } = buildConnectionAliasMap(conns)
    // C1 forward=A:B, sets fallback[A:B]=C1 and fallback[B:A]=C1 (reverse, first-seen guard)
    // C2 forward=B:A, always overwrites fallback[B:A]=C2;
    //   its reverse=A:B is already present so guard prevents overwrite → A:B stays C1
    expect(fallback.get('A:B')?.artifact_id).toBe('C1')
    expect(fallback.get('B:A')?.artifact_id).toBe('C2')
  })

  it('accumulates parallel edges in queue order', () => {
    const conns = [makeConn('A', 'B', 'C1'), makeConn('A', 'B', 'C2')]
    const { queue } = buildConnectionAliasMap(conns)
    expect(queue.get('A:B')).toEqual([conns[0], conns[1]])
  })
})

describe('resolveConnection', () => {
  it('returns undefined when alias map is empty', () => {
    const map = buildConnectionAliasMap([])
    expect(resolveConnection('A', 'B', map)).toBeUndefined()
  })

  it('resolves forward direction and consumes from queue', () => {
    const conn = makeConn('A', 'B', 'C1')
    const map = buildConnectionAliasMap([conn])
    expect(resolveConnection('A', 'B', map)?.artifact_id).toBe('C1')
    // consumed — second call returns undefined (queue empty, fallback still present)
    expect(resolveConnection('A', 'B', map)?.artifact_id).toBe('C1') // fallback
  })

  it('resolves reverse direction', () => {
    const conn = makeConn('A', 'B', 'C1')
    const map = buildConnectionAliasMap([conn])
    expect(resolveConnection('B', 'A', map)?.artifact_id).toBe('C1')
  })

  it('consumes parallel edges in order', () => {
    const c1 = makeConn('A', 'B', 'C1')
    const c2 = makeConn('A', 'B', 'C2')
    const map = buildConnectionAliasMap([c1, c2])
    expect(resolveConnection('A', 'B', map)?.artifact_id).toBe('C1')
    expect(resolveConnection('A', 'B', map)?.artifact_id).toBe('C2')
    // queue exhausted; fallback[A:B] was overwritten by each forward write → C2 (last processed)
    expect(resolveConnection('A', 'B', map)?.artifact_id).toBe('C2')
  })

  it('returns undefined for unknown pair', () => {
    const map = buildConnectionAliasMap([makeConn('A', 'B', 'C1')])
    expect(resolveConnection('X', 'Y', map)).toBeUndefined()
  })
})

// ── 2. Selection state machine ────────────────────────────────────────────────
//
// Models the same reactive logic as DiagramDetailView.vue's
// selectEntity / selectConnection / clearConnection without SVG DOM access.

type Conn = { artifact_id: string }

function makeSelectionState() {
  const selectedId = ref<string | null>(null)
  const selectedConn = ref<Conn | null>(null)

  const clearConnection = () => { selectedConn.value = null }

  const selectEntity = (id: string) => {
    clearConnection()
    if (selectedId.value === id) {
      selectedId.value = null
      return
    }
    selectedId.value = id
  }

  const selectConnection = (conn: Conn) => {
    selectedId.value = null
    const same = selectedConn.value?.artifact_id === conn.artifact_id
    clearConnection()
    if (!same) selectedConn.value = conn
  }

  return { selectedId, selectedConn, selectEntity, selectConnection, clearConnection }
}

describe('selection state — entity toggle', () => {
  it('selects an entity', () => {
    const { selectedId, selectEntity } = makeSelectionState()
    selectEntity('E1')
    expect(selectedId.value).toBe('E1')
  })

  it('deselects when same entity clicked twice', () => {
    const { selectedId, selectEntity } = makeSelectionState()
    selectEntity('E1')
    selectEntity('E1')
    expect(selectedId.value).toBeNull()
  })

  it('switches to a different entity', () => {
    const { selectedId, selectEntity } = makeSelectionState()
    selectEntity('E1')
    selectEntity('E2')
    expect(selectedId.value).toBe('E2')
  })
})

describe('selection state — connection toggle', () => {
  it('selects a connection', () => {
    const { selectedConn, selectConnection } = makeSelectionState()
    selectConnection({ artifact_id: 'C1' })
    expect(selectedConn.value?.artifact_id).toBe('C1')
  })

  it('deselects when same connection clicked twice', () => {
    const { selectedConn, selectConnection } = makeSelectionState()
    selectConnection({ artifact_id: 'C1' })
    selectConnection({ artifact_id: 'C1' })
    expect(selectedConn.value).toBeNull()
  })

  it('switches to a different connection', () => {
    const { selectedConn, selectConnection } = makeSelectionState()
    selectConnection({ artifact_id: 'C1' })
    selectConnection({ artifact_id: 'C2' })
    expect(selectedConn.value?.artifact_id).toBe('C2')
  })
})

describe('selection state — mutual exclusion', () => {
  it('selecting an entity clears active connection', () => {
    const { selectedConn, selectEntity, selectConnection } = makeSelectionState()
    selectConnection({ artifact_id: 'C1' })
    expect(selectedConn.value?.artifact_id).toBe('C1')
    selectEntity('E1')
    expect(selectedConn.value).toBeNull()
  })

  it('selecting a connection clears active entity', () => {
    const { selectedId, selectEntity, selectConnection } = makeSelectionState()
    selectEntity('E1')
    expect(selectedId.value).toBe('E1')
    selectConnection({ artifact_id: 'C1' })
    expect(selectedId.value).toBeNull()
  })
})

// ── 3. Derived C4 entities surface in the alias map ──────────────────────────
//
// C4 derived entities arrive in context.entities (not diagram_entities).
// buildAliasToId must include them so SVG node clicks resolve correctly.

describe('buildAliasToId — derived C4 entities (no host_diagram_id)', () => {
  it('maps model-backed C4 entity aliases (no host_diagram_id)', () => {
    const entities: EntitySummary[] = [
      makeEntity('APP@001.sys', 'MySystem'),
      makeEntity('APP@002.api', 'ApiGateway'),
    ]
    const map = buildAliasToId(entities)
    expect(map.get('MySystem')).toBe('APP@001.sys')
    expect(map.get('ApiGateway')).toBe('APP@002.api')
  })

  it('includes both model entities and diagram-only GSN nodes in a mixed list', () => {
    const GSN_ID = 'GSN@1234.abc.my-case'
    const entities: EntitySummary[] = [
      makeEntity('APP@001.sys', 'sys_A'),
      makeEntity(`${GSN_ID}#nodes/g1`, 'g1', GSN_ID),
    ]
    const map = buildAliasToId(entities)
    expect(map.get('sys_A')).toBe('APP@001.sys')
    expect(map.get('g1')).toBe(`${GSN_ID}#nodes/g1`)
  })

  it('produces PlantUML-safe aliases for both entity kinds', () => {
    const entities: EntitySummary[] = [makeEntity('APP@001.sys', 'My-System')]
    const map = buildAliasToId(entities)
    expect(map.get('My-System')).toBe('APP@001.sys')
    expect(map.get('My_System')).toBe('APP@001.sys')
  })

  it('mirrors the class-diagram renderer leading-underscore alias (_safe_alias)', () => {
    // Datatype classifiers carry their canonical id as display_alias; the renderer's SVG
    // node uses '_' + sanitised id, so that form must resolve to the canonical id.
    const entities: EntitySummary[] = [makeEntity('CLF@1.ShZ_Qq.artifact', 'CLF@1.ShZ_Qq.artifact')]
    const map = buildAliasToId(entities)
    expect(map.get('_CLF_1_ShZ_Qq_artifact')).toBe('CLF@1.ShZ_Qq.artifact')
  })

  it('prefers a canonical id over a diagram-scoped #fragment for the same alias', () => {
    const alias = 'CLF@1.ShZ_Qq.artifact'
    const entities: EntitySummary[] = [
      makeEntity(`DATATY@9.d#classifier/${alias}`, alias, 'DATATY@9.d'),
      makeEntity(alias, alias),
    ]
    const map = buildAliasToId(entities)
    // The non-fragment canonical id wins regardless of ordering — it is the one that loads.
    expect(map.get('_CLF_1_ShZ_Qq_artifact')).toBe(alias)
  })
})
