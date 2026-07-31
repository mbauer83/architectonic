import { describe, it, expect } from 'vitest'
import {
  analysisErrorMessage,
  buildAnalysisOptions,
  emptyNewAnalysisForm,
  findAnalysis,
  newAnalysisBody,
  validateNewAnalysis,
  nodesUrlForAnalysis,
  ANALYSIS_ANCHOR_TYPES,
  ANALYSIS_METHODS,
  ANALYSIS_STATUSES,
  type AnalysisSummary,
} from '../AssuranceAnalysisPicker.helpers'

/** A whole analysis record, because that is what the route sends — the fixtures used to carry three
 *  fields, which the summary type permitted while the server sent nine. */
const analysis = (fields: Pick<AnalysisSummary, 'analysis_id' | 'name' | 'method'>): AnalysisSummary => ({
  group_id: null,
  architecture_anchor_id: '',
  status: 'draft',
  tlp: 'TLP:WHITE',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  ...fields,
})

const sample: AnalysisSummary[] = [
  analysis({ analysis_id: 'STPA@1', name: 'Brakes', method: 'STPA' }),
  analysis({ analysis_id: 'GRC@2', name: 'Q3 Controls', method: 'GRC' }),
]

describe('buildAnalysisOptions', () => {
  it('tags labels with the method', () => {
    expect(buildAnalysisOptions(sample)).toEqual([
      { value: 'STPA@1', label: '[STPA] Brakes' },
      { value: 'GRC@2', label: '[GRC] Q3 Controls' },
    ])
  })

  it('handles an empty list', () => {
    expect(buildAnalysisOptions([])).toEqual([])
  })
})

describe('validateNewAnalysis', () => {
  it('accepts a valid form', () => {
    expect(validateNewAnalysis({ ...emptyNewAnalysisForm(), name: 'X' })).toBeNull()
  })

  it('rejects an empty name', () => {
    expect(validateNewAnalysis({ ...emptyNewAnalysisForm(), name: '  ' }))
      .toBe('Name is required.')
  })

  it('rejects an unknown method', () => {
    expect(validateNewAnalysis({ ...emptyNewAnalysisForm(), name: 'X', method: 'HAZOP' }))
      .toBe('Method must be STPA, CAST, or GRC.')
  })

  it('accepts every supported method', () => {
    for (const m of ANALYSIS_METHODS) {
      expect(validateNewAnalysis({ ...emptyNewAnalysisForm(), name: 'X', method: m })).toBeNull()
    }
  })
})

describe('newAnalysisBody', () => {
  it('trims fields and includes a non-empty anchor', () => {
    const body = newAnalysisBody({
      name: '  Brakes ', method: 'STPA',
      architecture_anchor_id: ' APP@1 ', tlp: 'TLP:AMBER',
    })
    expect(body).toEqual({
      name: 'Brakes', method: 'STPA', tlp: 'TLP:AMBER', architecture_anchor_id: 'APP@1',
    })
  })

  it('omits the anchor when empty (it is optional)', () => {
    const body = newAnalysisBody({
      name: 'Q3', method: 'GRC', architecture_anchor_id: '   ', tlp: 'TLP:WHITE',
    })
    expect(body).toEqual({ name: 'Q3', method: 'GRC', tlp: 'TLP:WHITE' })
    expect('architecture_anchor_id' in body).toBe(false)
  })
})

describe('emptyNewAnalysisForm', () => {
  it('defaults the method to STPA', () => {
    expect(emptyNewAnalysisForm().method).toBe('STPA')
  })

  it('honours an explicit default method', () => {
    expect(emptyNewAnalysisForm('GRC').method).toBe('GRC')
  })
})

describe('nodesUrlForAnalysis', () => {
  it('returns the unscoped url for null', () => {
    expect(nodesUrlForAnalysis(null)).toBe('/api/assurance/nodes')
  })

  it('encodes the analysis id', () => {
    expect(nodesUrlForAnalysis('STPA@1.a/b'))
      .toBe('/api/assurance/nodes?analysis_id=STPA%401.a%2Fb')
  })

  it('carries a requested order, with or without an analysis scope', () => {
    expect(nodesUrlForAnalysis(null, 'updated_at', 'desc'))
      .toBe('/api/assurance/nodes?sort=updated_at&order=desc')
    expect(nodesUrlForAnalysis('STPA@1', 'name', 'asc'))
      .toBe('/api/assurance/nodes?analysis_id=STPA%401&sort=name&order=asc')
  })
})

describe('findAnalysis', () => {
  it('returns the matching summary', () => {
    expect(findAnalysis(sample, 'GRC@2')?.name).toBe('Q3 Controls')
  })

  it('returns null for a missing id or null selection', () => {
    expect(findAnalysis(sample, 'nope')).toBeNull()
    expect(findAnalysis(sample, null)).toBeNull()
  })
})

describe('analysisErrorMessage', () => {
  it('prefers the server message', () => {
    expect(analysisErrorMessage({ message: 'still owns 3 node(s)' }, 400))
      .toBe('still owns 3 node(s)')
  })

  it('falls back to the HTTP status', () => {
    expect(analysisErrorMessage({}, 409)).toBe('HTTP 409')
  })
})

describe('ANALYSIS_STATUSES', () => {
  it('matches the backend status vocabulary', () => {
    expect([...ANALYSIS_STATUSES]).toEqual(['draft', 'active', 'completed', 'archived'])
  })
})

describe('ANALYSIS_ANCHOR_TYPES', () => {
  it('are ArchiMate (model) types, never C4 view elements', () => {
    const types = [...ANALYSIS_ANCHOR_TYPES]
    expect(types).toContain('application-component')
    expect(types.some((t) => t.startsWith('c4-'))).toBe(false)
    expect(types).not.toContain('container')
    expect(types).not.toContain('system')
  })
})
