/**
 * Authorship and participation, as the node-detail response carries them.
 *
 * Two different facts about one node, and a reader who cannot tell them apart cannot tell a native
 * finding from one another method contributed — which is the whole reason the store keeps the two
 * relations separate instead of collapsing them into one `analysis_id`.
 *
 * The decisions live here rather than in the template so they can be tested: whether there is any
 * provenance to show at all, and where an analysis link goes.
 */

/** Enough of an analysis to label and link it; the analysis itself has its own endpoint. */
export interface AssuranceAnalysisSummary {
  analysis_id: string
  name: string
  method: string
  status?: string
  group_id?: string | null
}

/** The two provenance fields every assurance node-detail response carries. */
export interface AssuranceProvenanceFields {
  /** The analysis that produced this node, or null when it has none this reader can see. */
  authored_by: AssuranceAnalysisSummary | null
  /** Analyses that draw on the node without having authored it. Never includes the author. */
  participates_in: AssuranceAnalysisSummary[]
}

/** A response that predates these fields, or one from a store with no analyses, still renders. */
export const provenanceOf = (
  response: Partial<AssuranceProvenanceFields> | null | undefined,
): AssuranceProvenanceFields => ({
  authored_by: response?.authored_by ?? null,
  participates_in: response?.participates_in ?? [],
})

/**
 * Whether to render the section at all.
 *
 * False renders nothing rather than an empty "Provenance" heading: a heading with nothing under it
 * asserts that the node *has* no provenance, which is a different claim from "none you can see" —
 * and the second is what a reader below the analysis' classification ceiling is being told.
 */
export const hasProvenance = (fields: AssuranceProvenanceFields): boolean =>
  fields.authored_by !== null || fields.participates_in.length > 0

/** Where an analysis chip goes: the browse surface, scoped to that analysis. */
export const analysisRoute = (analysisId: string) => ({
  path: '/assurance',
  query: { analysis: analysisId },
})

/** The label for the borrowers list. "Also used by", never "belongs to": these analyses reason
 * over the node without owning it, and no copy of it exists anywhere. */
export const BORROWERS_LABEL = 'Also used by'

/** The label for the single authoring analysis. */
export const AUTHOR_LABEL = 'Authored by'
