import { describe, it, expect } from 'vitest'
import { Schema } from 'effect'
import { EntitySummarySchema } from './entities'
import { DocumentSummarySchema } from './documents'
import { DiagramSummarySchema } from './diagram-types'

/**
 * List-summary contracts: `is_global` is REQUIRED on entity, document and diagram list rows — the
 * backend always emits it, and a row without it must fail the decode rather than render a default.
 *
 * What the badge *derives* from it is asserted in `ui/components/__tests__/TierBadge.helpers.test.ts`,
 * which owns that helper. Re-asserting it here duplicated a covered rule and reached from the domain
 * into the delivery layer to do it — the layering rule in `eslint.config.js` now refuses that.
 */

const ENTITY_ROW = {
  artifact_id: 'REQ@1000000901.CtrRow.contract-row',
  artifact_type: 'requirement',
  name: 'Contract Row',
  version: '0.1.0',
  status: 'draft',
  domain: 'motivation',
  subdomain: 'requirement',
  path: '/repo/model/motivation/requirement/row.md',
}

const DOCUMENT_ROW = {
  artifact_id: 'ADR@1000000902.CtrDoc.contract-document',
  doc_type: 'adr',
  title: 'Contract Document',
  status: 'draft',
  path: '/repo/docs/adr/contract-document.md',
  keywords: [],
  sections: [],
  group: 'decisions',
}

const DIAGRAM_ROW = {
  artifact_id: 'ARC@1000000903.CtrDia.contract-diagram',
  name: 'Contract Diagram',
  diagram_type: 'archimate-motivation',
  version: '0.1.0',
  status: 'draft',
  path: '/repo/diagram-catalog/diagrams/contract-diagram.puml',
  group: 'views',
}

describe('entity list summary contract', () => {
  it('accepts both badge variants', () => {
    for (const isGlobal of [true, false]) {
      const decoded = Schema.decodeUnknownSync(EntitySummarySchema)({ ...ENTITY_ROW, is_global: isGlobal })
      expect(decoded.is_global).toBe(isGlobal)
    }
  })

  it('rejects a row without is_global — the contract is closed', () => {
    expect(() => Schema.decodeUnknownSync(EntitySummarySchema)(ENTITY_ROW)).toThrow()
  })
})

describe('document list summary contract', () => {
  it('accepts both badge variants', () => {
    for (const isGlobal of [true, false]) {
      const decoded = Schema.decodeUnknownSync(DocumentSummarySchema)({ ...DOCUMENT_ROW, is_global: isGlobal })
      expect(decoded.is_global).toBe(isGlobal)
    }
  })

  it('rejects a row without is_global — the contract is closed', () => {
    expect(() => Schema.decodeUnknownSync(DocumentSummarySchema)(DOCUMENT_ROW)).toThrow()
  })
})

describe('diagram list summary contract', () => {
  it('accepts both badge variants', () => {
    for (const isGlobal of [true, false]) {
      const decoded = Schema.decodeUnknownSync(DiagramSummarySchema)({ ...DIAGRAM_ROW, is_global: isGlobal })
      expect(decoded.is_global).toBe(isGlobal)
    }
  })

  it('rejects a row without is_global — the contract is closed', () => {
    expect(() => Schema.decodeUnknownSync(DiagramSummarySchema)(DIAGRAM_ROW)).toThrow()
  })
})

/**
 * The modification stamp is optional and nullable on every list row: an artifact with no
 * `last-updated` frontmatter (or a repository predating the field) still has to decode, and
 * the row renders a placeholder rather than failing the whole list.
 */
describe('last-modified stamp on list summaries', () => {
  const STAMP = '2026-07-24T09:15:00Z'

  it('accepts a stamped and an unstamped entity row', () => {
    const row = { ...ENTITY_ROW, is_global: false }
    expect(Schema.decodeUnknownSync(EntitySummarySchema)({ ...row, last_updated: STAMP }).last_updated).toBe(STAMP)
    expect(Schema.decodeUnknownSync(EntitySummarySchema)({ ...row, last_updated: null }).last_updated).toBeNull()
    expect(Schema.decodeUnknownSync(EntitySummarySchema)(row).last_updated).toBeUndefined()
  })

  it('accepts a stamped and an unstamped document row', () => {
    const row = { ...DOCUMENT_ROW, is_global: false }
    expect(Schema.decodeUnknownSync(DocumentSummarySchema)({ ...row, last_updated: STAMP }).last_updated).toBe(STAMP)
    expect(Schema.decodeUnknownSync(DocumentSummarySchema)({ ...row, last_updated: null }).last_updated).toBeNull()
    expect(Schema.decodeUnknownSync(DocumentSummarySchema)(row).last_updated).toBeUndefined()
  })

  it('accepts a stamped and an unstamped diagram row', () => {
    const row = { ...DIAGRAM_ROW, is_global: false }
    expect(Schema.decodeUnknownSync(DiagramSummarySchema)({ ...row, last_updated: STAMP }).last_updated).toBe(STAMP)
    expect(Schema.decodeUnknownSync(DiagramSummarySchema)({ ...row, last_updated: null }).last_updated).toBeNull()
    expect(Schema.decodeUnknownSync(DiagramSummarySchema)(row).last_updated).toBeUndefined()
  })
})
