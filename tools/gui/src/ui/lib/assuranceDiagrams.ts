/**
 * The catalog of assurance projections the store can render.
 *
 * Both the overview (which lists them) and a detail page (which names the one it is showing)
 * need the same catalog, and both have to handle a locked store the same way — so the fetch and
 * its failure vocabulary live here rather than being written twice.
 *
 * **An entry is an analysis crossed with a diagram type, not a type on its own.** A derived diagram
 * belongs to a unit of work: one control structure per STPA, one matrix per FMEA. Keyed by type
 * alone there is a single slot per type for the whole store, so a second FMEA has nowhere to put
 * its matrix and asking for "the" matrix asks for a drawing of every analysis at once.
 *
 * The `diagram_id` the backend hands out is that pair, and it is treated as opaque here: routes
 * carry the analysis and the type as separate values because the render endpoint takes them
 * separately, and re-deriving them by splitting a composite id would be a second implementation
 * of a key we were given.
 */
import { assuranceAnalysisDiagramRoute } from '../router/artifactRoutes'

export interface AssuranceDiagramMeta {
  /** Opaque identity of the pair, as issued by the backend. Used for keys, never parsed. */
  diagram_id: string
  analysis_id: string
  analysis_name: string
  method: string
  diagram_type: string
  /** The analysis' name — what a reader with several analyses open actually needs. */
  title: string
  /** The diagram type's own label, from its config. */
  type_label: string
  description: string
}

export interface AssuranceDiagramCatalog {
  diagrams: AssuranceDiagramMeta[]
  /** Reader-facing failure text, or null when the catalog loaded. */
  error: string | null
}

export const STORE_LOCKED = 'Store is locked.'

export async function fetchAssuranceDiagrams(): Promise<AssuranceDiagramCatalog> {
  try {
    const response = await fetch('/api/assurance/diagrams')
    if (response.status === 423) return { diagrams: [], error: STORE_LOCKED }
    if (!response.ok) return { diagrams: [], error: `HTTP ${response.status}` }
    const body = await response.json() as { diagrams?: AssuranceDiagramMeta[] }
    return { diagrams: body.diagrams ?? [], error: null }
  } catch (cause) {
    return { diagrams: [], error: String(cause) }
  }
}

/** The route a diagram card opens: the analysis and the type, which is what the render call needs. */
export const diagramDetailRoute = (analysisId: string, diagramType: string) => ({
  path: assuranceAnalysisDiagramRoute(analysisId, diagramType),
})

/** The endpoint that renders one analysis' projection of one type. */
export const renderedDiagramUrl = (analysisId: string, diagramType: string): string =>
  `/api/assurance/analyses/${encodeURIComponent(analysisId)}`
  + `/diagrams/${encodeURIComponent(diagramType)}/rendered`

/** The requested diagram if the catalog has it, else null — a stale bookmark names a projection
 * that may no longer exist (its analysis deleted, or its type no longer applicable), and the
 * reader should be told rather than shown an empty canvas. */
export const findDiagram = (
  diagrams: readonly AssuranceDiagramMeta[],
  analysisId: string | null,
  diagramType: string | null,
): AssuranceDiagramMeta | null =>
  diagrams.find(
    (diagram) => diagram.analysis_id === analysisId && diagram.diagram_type === diagramType,
  ) ?? null

/** The catalog grouped by analysis, in first-seen order, so the overview reads as a list of
 * analyses rather than a flat grid in which the same four titles repeat. */
export interface AssuranceDiagramGroup {
  analysisId: string
  analysisName: string
  method: string
  diagrams: AssuranceDiagramMeta[]
}

export const groupByAnalysis = (
  diagrams: readonly AssuranceDiagramMeta[],
): AssuranceDiagramGroup[] => {
  const groups = new Map<string, AssuranceDiagramGroup>()
  for (const diagram of diagrams) {
    const existing = groups.get(diagram.analysis_id)
    if (existing) {
      existing.diagrams.push(diagram)
      continue
    }
    groups.set(diagram.analysis_id, {
      analysisId: diagram.analysis_id,
      analysisName: diagram.analysis_name || diagram.analysis_id,
      method: diagram.method,
      diagrams: [diagram],
    })
  }
  return [...groups.values()]
}
