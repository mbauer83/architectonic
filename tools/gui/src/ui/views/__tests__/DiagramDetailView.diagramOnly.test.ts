/**
 * Tests for WU-E5: diagram-only entity selection in DiagramDetailView.
 *
 * Covers the three testable layers without full component mounting:
 *  1. Schema decoding — artifact_type and host_diagram_id survive the wire codec.
 *  2. buildAliasToId — GSN node_id aliases are present in the interactivity map.
 *  3. isDiagramOnly — predicate correctly identifies host-diagram-owned entities.
 *
 * SVG click→selectEntity requires a browser-rendered SVG; that path is exercised
 * by Playwright (as with the C4 drill-down badge).
 */
import { describe, it, expect } from 'vitest'
import { Schema } from 'effect'
import { EntitySummarySchema, EntityDetailSchema } from '../../../domain/schemas'
import { buildAliasToId, isDiagramOnly } from '../DiagramDetailView.helpers'
import type { EntitySummary } from '../../../domain'

// ── 1. Schema decoding ───────────────────────────────────────────────────────

const GSN_ID = 'GSN@1234567890.gSnXxX.my-assurance-case'

const gsnNodeSummaryRaw = {
  artifact_id: `${GSN_ID}#nodes/g1`,
  artifact_type: 'nodes',
  name: 'The system is acceptably secure',
  version: '0.1.0',
  status: 'draft',
  domain: 'gsn',
  subdomain: 'nodes',
  path: '/tmp/my-assurance-case.puml',
  is_global: false,
  group: 'uncategorized',
  host_diagram_id: GSN_ID,
}

const gsnNodeDetailRaw = {
  ...gsnNodeSummaryRaw,
  record_type: 'entity' as const,
  content_snippet: 'The system is acceptably secure',
  content_text: 'The system is acceptably secure goal',
  extra: { gsn_type: 'goal' },
}

describe('EntitySummarySchema — diagram-only entity', () => {
  it('decodes artifact_type "nodes" (non-standard type key)', () => {
    const decoded = Schema.decodeUnknownSync(EntitySummarySchema)(gsnNodeSummaryRaw)
    expect(decoded.artifact_type).toBe('nodes')
  })

  it('preserves host_diagram_id on decode', () => {
    const decoded = Schema.decodeUnknownSync(EntitySummarySchema)(gsnNodeSummaryRaw)
    expect(decoded.host_diagram_id).toBe(GSN_ID)
  })

  it('host_diagram_id is absent (undefined) for model entities', () => {
    const modelRaw = { ...gsnNodeSummaryRaw, artifact_type: 'goal', host_diagram_id: undefined }
    const decoded = Schema.decodeUnknownSync(EntitySummarySchema)(modelRaw)
    expect(decoded.host_diagram_id).toBeUndefined()
  })
})

describe('EntityDetailSchema — diagram-only entity', () => {
  it('decodes artifact_type "nodes"', () => {
    const decoded = Schema.decodeUnknownSync(EntityDetailSchema)(gsnNodeDetailRaw)
    expect(decoded.artifact_type).toBe('nodes')
  })

  it('preserves host_diagram_id', () => {
    const decoded = Schema.decodeUnknownSync(EntityDetailSchema)(gsnNodeDetailRaw)
    expect(decoded.host_diagram_id).toBe(GSN_ID)
  })
})

// ── 2. buildAliasToId — alias map includes diagram-only node aliases ──────────

const makeEntity = (artifactId: string, display_alias: string, host_diagram_id?: string): EntitySummary => ({
  artifact_id: artifactId,
  artifact_type: 'nodes',
  name: 'Test',
  version: '0.1.0',
  status: 'draft',
  domain: 'gsn',
  subdomain: 'nodes',
  path: '/tmp/diag.puml',
  is_global: false,
  group: 'uncategorized',
  display_alias,
  host_diagram_id,
})

describe('buildAliasToId — GSN diagram-only entities', () => {
  it('maps node_id alias to full artifact_id', () => {
    const entities = [
      makeEntity(`${GSN_ID}#nodes/g1`, 'g1', GSN_ID),
      makeEntity(`${GSN_ID}#nodes/s1`, 's1', GSN_ID),
      makeEntity(`${GSN_ID}#nodes/cx1`, 'cx1', GSN_ID),
    ]
    const map = buildAliasToId(entities)
    expect(map.get('g1')).toBe(`${GSN_ID}#nodes/g1`)
    expect(map.get('s1')).toBe(`${GSN_ID}#nodes/s1`)
    expect(map.get('cx1')).toBe(`${GSN_ID}#nodes/cx1`)
  })

  it('also stores PlantUML-safe variant (non-alphanumeric → underscore)', () => {
    const entities = [makeEntity(`${GSN_ID}#nodes/cx1`, 'cx-1', GSN_ID)]
    const map = buildAliasToId(entities)
    expect(map.get('cx-1')).toBe(`${GSN_ID}#nodes/cx1`)
    expect(map.get('cx_1')).toBe(`${GSN_ID}#nodes/cx1`)
  })

  it('returns empty map when no entities have display_alias', () => {
    const entities = [{ ...makeEntity('id1', ''), display_alias: undefined } as unknown as EntitySummary]
    expect(buildAliasToId(entities).size).toBe(0)
  })

  it('works alongside model entities in the same list', () => {
    const entities = [
      makeEntity('BUS@0001.AAAAAA.system', 'sys_A'),
      makeEntity(`${GSN_ID}#nodes/g1`, 'g1', GSN_ID),
    ]
    const map = buildAliasToId(entities)
    expect(map.size).toBeGreaterThanOrEqual(2)
    expect(map.get('sys_A')).toBe('BUS@0001.AAAAAA.system')
    expect(map.get('g1')).toBe(`${GSN_ID}#nodes/g1`)
  })
})

// ── 3. isDiagramOnly ─────────────────────────────────────────────────────────

describe('isDiagramOnly', () => {
  it('returns true when host_diagram_id is set', () => {
    expect(isDiagramOnly({ host_diagram_id: GSN_ID })).toBe(true)
  })

  it('returns false when host_diagram_id is undefined', () => {
    expect(isDiagramOnly({ host_diagram_id: undefined })).toBe(false)
  })

  it('returns false when host_diagram_id is null', () => {
    expect(isDiagramOnly({ host_diagram_id: null })).toBe(false)
  })

  it('returns false when host_diagram_id is empty string', () => {
    expect(isDiagramOnly({ host_diagram_id: '' })).toBe(false)
  })
})
