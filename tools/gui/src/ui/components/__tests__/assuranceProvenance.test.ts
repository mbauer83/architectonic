/**
 * A borrowed node has to look borrowed.
 *
 * Authorship and participation are two facts, and a reader who cannot tell them apart cannot tell a
 * native finding from one another method contributed — which is the whole reason the store keeps the
 * two relations separate instead of collapsing them into one `analysis_id`.
 */
import { describe, expect, it } from 'vitest'
import {
  AUTHOR_LABEL,
  BORROWERS_LABEL,
  analysisRoute,
  hasProvenance,
  provenanceOf,
  type AssuranceAnalysisSummary,
} from '../AssuranceProvenance.helpers'

const STPA: AssuranceAnalysisSummary = {
  analysis_id: 'STPA@1.aaaa.000001',
  name: 'Key availability',
  method: 'STPA',
}
const FMEA: AssuranceAnalysisSummary = {
  analysis_id: 'FMEA@1.bbbb.000002',
  name: 'Credential backend',
  method: 'FMEA',
}

describe('provenanceOf', () => {
  it('reads both fields off a response', () => {
    const fields = provenanceOf({ authored_by: STPA, participates_in: [FMEA] })

    expect(fields.authored_by).toEqual(STPA)
    expect(fields.participates_in).toEqual([FMEA])
  })

  it('tolerates a response without the fields, so a node still renders', () => {
    expect(provenanceOf({})).toEqual({ authored_by: null, participates_in: [] })
    expect(provenanceOf(null)).toEqual({ authored_by: null, participates_in: [] })
    expect(provenanceOf(undefined)).toEqual({ authored_by: null, participates_in: [] })
  })
})

describe('hasProvenance', () => {
  it('is true for a node with an author', () => {
    expect(hasProvenance({ authored_by: STPA, participates_in: [] })).toBe(true)
  })

  it('is true for a node only borrowers can be seen for', () => {
    /* An author above the reader's ceiling is absent, but the borrowers this reader may see are
       still worth showing. */
    expect(hasProvenance({ authored_by: null, participates_in: [FMEA] })).toBe(true)
  })

  it('is false when there is nothing to say', () => {
    /* Rendering an empty "Provenance" heading would assert that the node *has* no provenance,
       which is a different claim from "none you can see". */
    expect(hasProvenance({ authored_by: null, participates_in: [] })).toBe(false)
  })
})

describe('analysisRoute', () => {
  it('opens the browse surface scoped to that analysis', () => {
    expect(analysisRoute(STPA.analysis_id)).toEqual({
      path: '/assurance',
      query: { analysis: STPA.analysis_id },
    })
  })
})

describe('the labels', () => {
  it('distinguish owning from using', () => {
    /* "Also used by", never "belongs to": a borrower reasons over the node without owning it, and
       no copy of it exists anywhere. */
    expect(AUTHOR_LABEL).toBe('Authored by')
    expect(BORROWERS_LABEL).toBe('Also used by')
    expect(BORROWERS_LABEL.toLowerCase()).not.toContain('belongs')
  })
})
