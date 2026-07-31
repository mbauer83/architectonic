/**
 * Pure logic for the ontology-driven edge picker: the served edge catalog is
 * the ONLY source of offered connection types (no literal list exists in the
 * frontend), filtered to the legal set for the concrete (source, target)
 * node-type pair in the chosen direction.
 *
 * **Candidates range over the whole visible store, never over one analysis.** The analysis method
 * constrains what may be *authored*; it must not constrain what may be *referenced*. An FMEA
 * proposes failure modes, and the hazard each one leads to belongs to the STPA that identified it —
 * narrowing the picker to the current analysis would make that edge unauthorable and leave copying
 * the STPA's nodes as the only way through, which is exactly the drift the three-relation model
 * exists to prevent. So the label below *shows* which analysis a candidate comes from rather than
 * filtering candidates by it: crossing methods stays possible, and becomes deliberate.
 */

import type { AssuranceAnalysisSummary } from '../../domain/schemas/assurance-analyses'

export interface EdgeCatalogRow {
  source_type: string
  target_type: string
  connection_types: string[]
}

export interface EdgeCatalog {
  edge_types: { name: string; label: string }[]
  permitted: EdgeCatalogRow[]
  reference_types: { name: string; description: string }[]
}

export type EdgeDirection = 'outgoing' | 'incoming'

/** The authoring analysis a search hit carries, when the reader may see it — the summary the route
 *  sends, not a three-field restatement of it. */
export type HitAnalysis = AssuranceAnalysisSummary

/**
 * How a candidate is labelled in the result list.
 *
 * The owning analysis is named when there is one, so an author reaching across methods can see
 * that they are doing so. A hit with no visible analysis says nothing about it: the node is
 * legitimately reachable, and its analysis being above the reader's ceiling is not the reader's
 * problem to solve here.
 */
export const candidateProvenance = (analysis: HitAnalysis | null | undefined): string =>
  analysis ? `${analysis.method} · ${analysis.name}` : ''

/** Whether picking this candidate crosses from the authoring analysis into another's work. */
export const isCrossAnalysis = (
  panelAnalysisId: string | null | undefined,
  analysis: HitAnalysis | null | undefined,
): boolean =>
  Boolean(panelAnalysisId) && Boolean(analysis) && analysis!.analysis_id !== panelAnalysisId

export const legalTypesForPair = (
  catalog: EdgeCatalog,
  sourceType: string,
  targetType: string,
): string[] => {
  const row = catalog.permitted.find(
    (r) => r.source_type === sourceType && r.target_type === targetType,
  )
  return row ? [...row.connection_types] : []
}

/** The legal set for the picker's current selection: for an incoming edge the
 * searched node is the SOURCE and the panel's node the target. */
export const legalTypesForSelection = (
  catalog: EdgeCatalog,
  direction: EdgeDirection,
  panelNodeType: string,
  otherNodeType: string,
): string[] =>
  direction === 'outgoing'
    ? legalTypesForPair(catalog, panelNodeType, otherNodeType)
    : legalTypesForPair(catalog, otherNodeType, panelNodeType)

export const emptyLegalSetMessage = (
  direction: EdgeDirection,
  panelNodeType: string,
  otherNodeType: string,
): string => {
  const [from, to] = direction === 'outgoing'
    ? [panelNodeType, otherNodeType]
    : [otherNodeType, panelNodeType]
  return `No edge type is legal from ${from} to ${to}. `
    + 'Architecture references (e.g. evidence bindings) go through the arch-reference form instead.'
}

/** Source/target ids for submission, honoring the direction. */
export const edgeSubmission = (
  direction: EdgeDirection,
  panelNodeId: string,
  otherNodeId: string,
  connType: string,
): { source_id: string; target_id: string; conn_type: string } =>
  direction === 'outgoing'
    ? { source_id: panelNodeId, target_id: otherNodeId, conn_type: connType }
    : { source_id: otherNodeId, target_id: panelNodeId, conn_type: connType }
