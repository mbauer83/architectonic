/**
 * A derived assurance diagram is identified by its analysis *and* its type.
 *
 * Keyed by type alone there is one slot per type for the whole store: a second FMEA has nowhere to
 * put its matrix, and asking for "the" FMEA matrix asks for a drawing of every analysis at once.
 * These tests hold the pair together through the route, the render URL and the lookup.
 */
import { describe, expect, it } from 'vitest'
import {
  diagramDetailRoute,
  findDiagram,
  groupByAnalysis,
  renderedDiagramUrl,
  type AssuranceDiagramMeta,
} from '../assuranceDiagrams'
import { assuranceAnalysisDiagramRoute } from '../../router/artifactRoutes'

const entry = (
  analysisId: string,
  analysisName: string,
  method: string,
  diagramType: string,
  typeLabel: string,
): AssuranceDiagramMeta => ({
  diagram_id: `${analysisId}::${diagramType}`,
  analysis_id: analysisId,
  analysis_name: analysisName,
  method,
  diagram_type: diagramType,
  title: analysisName,
  type_label: typeLabel,
  description: `${typeLabel} description`,
})

const STPA = 'STPA@1.aaaa.000001'
const FMEA_ONE = 'FMEA@1.bbbb.000002'
const FMEA_TWO = 'FMEA@1.cccc.000003'

const CATALOG: AssuranceDiagramMeta[] = [
  entry(STPA, 'Key availability', 'STPA', 'control-structure', 'Control Structure'),
  entry(STPA, 'Key availability', 'STPA', 'bowtie', 'Bowtie'),
  entry(FMEA_ONE, 'Credential backend', 'FMEA', 'fmea-matrix', 'FMEA Matrix'),
  entry(FMEA_TWO, 'Key rotation service', 'FMEA', 'fmea-matrix', 'FMEA Matrix'),
]

describe('diagramDetailRoute', () => {
  it('carries the analysis and the type, which is what the render call needs', () => {
    expect(diagramDetailRoute(STPA, 'bowtie')).toEqual({
      path: assuranceAnalysisDiagramRoute(STPA, 'bowtie'),
    })
  })
})

describe('renderedDiagramUrl', () => {
  it('addresses the projection under its analysis', () => {
    expect(renderedDiagramUrl(STPA, 'bowtie')).toBe(
      `/api/assurance/analyses/${encodeURIComponent(STPA)}/diagrams/bowtie/rendered`,
    )
  })

  it('encodes both halves, so an id with a reserved character still resolves', () => {
    expect(renderedDiagramUrl('STPA@1.a/b', 'uca-matrix')).toBe(
      '/api/assurance/analyses/STPA%401.a%2Fb/diagrams/uca-matrix/rendered',
    )
  })
})

describe('findDiagram', () => {
  it('resolves a projection from the pair', () => {
    expect(findDiagram(CATALOG, STPA, 'bowtie')?.type_label).toBe('Bowtie')
  })

  it('tells two analyses of the same type apart', () => {
    expect(findDiagram(CATALOG, FMEA_ONE, 'fmea-matrix')?.title).toBe('Credential backend')
    expect(findDiagram(CATALOG, FMEA_TWO, 'fmea-matrix')?.title).toBe('Key rotation service')
  })

  it('returns null when the type is not drawn for that analysis', () => {
    expect(findDiagram(CATALOG, STPA, 'fmea-matrix')).toBeNull()
  })

  it('returns null for a stale bookmark or a missing query, so the page can say so', () => {
    expect(findDiagram(CATALOG, 'STPA@gone', 'bowtie')).toBeNull()
    expect(findDiagram(CATALOG, null, 'bowtie')).toBeNull()
    expect(findDiagram(CATALOG, STPA, null)).toBeNull()
    expect(findDiagram([], STPA, 'bowtie')).toBeNull()
  })
})

describe('groupByAnalysis', () => {
  it('groups so the overview reads as a list of analyses, not a grid of repeated titles', () => {
    const groups = groupByAnalysis(CATALOG)

    expect(groups.map((group) => group.analysisId)).toEqual([STPA, FMEA_ONE, FMEA_TWO])
    expect(groups[0].diagrams.map((diagram) => diagram.diagram_type)).toEqual([
      'control-structure',
      'bowtie',
    ])
  })

  it('keeps each analysis its own group even when two share a type', () => {
    const groups = groupByAnalysis(CATALOG)

    expect(groups[1].analysisName).toBe('Credential backend')
    expect(groups[2].analysisName).toBe('Key rotation service')
  })

  it('falls back to the id when an analysis has no name', () => {
    const nameless = { ...entry(STPA, '', 'STPA', 'bowtie', 'Bowtie'), analysis_name: '' }

    expect(groupByAnalysis([nameless])[0].analysisName).toBe(STPA)
  })

  it('has no groups for an empty catalog', () => {
    expect(groupByAnalysis([])).toEqual([])
  })
})
