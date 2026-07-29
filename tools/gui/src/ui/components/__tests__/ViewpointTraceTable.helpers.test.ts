import { describe, expect, it } from 'vitest'

import {
  traceColumns,
  traceDerivationNote,
  traceDisplayRows,
  traceTruncationNote,
  verdictTone,
} from '../ViewpointTraceTable.helpers'

const authoritative = (verdict: string, status: string) => ({
  role: 'authoritative' as const,
  verdict: verdict as 'pass' | 'gap' | 'not_applicable',
  status_code: status,
  coverage: { covered: 2, applicable: 3 },
  incomplete_branch_count: 0,
  failing_obligations: [],
  failing_overflow: 0,
  last_satisfied_ids: ['REQ@1'],
  missing_expected: ['requirement'],
  shortcut: false,
  diagnostic_code: null,
})

const diagnostic = (observation: 'observed' | 'none_observed' | 'not_applicable') => ({
  role: 'diagnostic' as const,
  observation,
  last_satisfied_ids: [],
})

const table = (overrides: Record<string, unknown> = {}) =>
  ({
    rows: [
      {
        entity_id: 'GOL@1',
        entity_type: 'goal',
        name: 'Alpha',
        tier: 'engagement',
        verdict: 'gap' as const,
        pattern_results: [
          ['motivation', authoritative('gap', 'shortcut')],
          ['business_coverage', diagnostic('none_observed')],
        ],
      },
    ],
    total_rows: 1,
    returned_rows: 1,
    truncated: false,
    derived_truncated: false,
    ...overrides,
  }) as never

describe('traceColumns', () => {
  it('derives one column per declared pattern, carrying its role', () => {
    expect(traceColumns(table())).toEqual([
      { key: 'motivation', label: 'Motivation', role: 'authoritative' },
      { key: 'business_coverage', label: 'Business Coverage', role: 'diagnostic' },
    ])
  })

  it('is empty for no table', () => {
    expect(traceColumns(null)).toEqual([])
  })
})

describe('traceDisplayRows', () => {
  it('renders an authoritative cell with status and coverage as TEXT', () => {
    const [row] = traceDisplayRows(table())
    expect(row.cells[0].text).toBe('shortcut 2/3')
    expect(row.cells[0].tone).toBe('negative')
    expect(row.cells[0].detail).toContain('missing requirement')
  })

  it('never gives a diagnostic observation a verdict tone', () => {
    // The whole point of the diagnostic role: absence of a business-layer realizer is not a
    // gap, so it must not be coloured like one.
    const [row] = traceDisplayRows(table())
    expect(row.cells[1].text).toBe('none observed')
    expect(row.cells[1].tone).toBe('neutral')
  })

  it('carries the composed row verdict', () => {
    const [row] = traceDisplayRows(table())
    expect(row.verdict).toBe('gap')
    expect(row.tone).toBe('negative')
  })
})

describe('verdictTone', () => {
  it('maps verdicts to weights, leaving not_applicable neutral', () => {
    expect(verdictTone('gap')).toBe('negative')
    expect(verdictTone('pass')).toBe('positive')
    expect(verdictTone('not_applicable')).toBe('neutral')
  })
})

describe('notes', () => {
  it('states truncation against the pre-limit total so a hidden gap is not implied absent', () => {
    const note = traceTruncationNote(table({ truncated: true, returned_rows: 1, total_rows: 9 }))
    expect(note).toContain('1 of 9')
  })

  it('warns that coverage is a lower bound when the traversal was cut short', () => {
    expect(traceDerivationNote(table({ derived_truncated: true }))).toContain('lower bound')
  })

  it('is silent when nothing was truncated', () => {
    expect(traceTruncationNote(table())).toBe('')
    expect(traceDerivationNote(table())).toBe('')
  })
})
