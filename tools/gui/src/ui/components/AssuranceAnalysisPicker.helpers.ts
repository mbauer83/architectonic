// Pure helpers for the assurance analysis picker — unit-testable without a DOM.

export const ANALYSIS_METHODS = ['STPA', 'CAST', 'GRC'] as const
export type AnalysisMethod = (typeof ANALYSIS_METHODS)[number]

export const ANALYSIS_STATUSES = ['draft', 'active', 'completed', 'archived'] as const
export type AnalysisStatus = (typeof ANALYSIS_STATUSES)[number]

/**
 * Admissible ArchiMate anchor types for an analysis's system-under-analysis.
 * Expressed in ArchiMate terms (never a C4 view element): a service →
 * application-component; a system or subset → application-collaboration/grouping;
 * technology → node/system-software. Keeps the anchor a real model entity rather
 * than free text.
 */
export const ANALYSIS_ANCHOR_TYPES = [
  'application-component',
  'application-collaboration',
  'grouping',
  'node',
  'system-software',
] as const

export interface AnalysisSummary {
  analysis_id: string
  name: string
  method: string
  status?: string
  tlp?: string
  architecture_anchor_id?: string
}

export interface AnalysisOption {
  value: string
  label: string
}

/** Build `<option>` entries for the analysis dropdown (method-tagged labels). */
export function buildAnalysisOptions(analyses: AnalysisSummary[]): AnalysisOption[] {
  return analyses.map((a) => ({ value: a.analysis_id, label: `[${a.method}] ${a.name}` }))
}

export interface NewAnalysisForm {
  name: string
  method: string
  architecture_anchor_id: string
  tlp: string
}

export function emptyNewAnalysisForm(method: AnalysisMethod = 'STPA'): NewAnalysisForm {
  return { name: '', method, architecture_anchor_id: '', tlp: 'TLP:WHITE' }
}

/** Mirror the backend invariants so the form blocks before a doomed POST. */
export function validateNewAnalysis(form: NewAnalysisForm): string | null {
  if (!form.name.trim()) return 'Name is required.'
  if (!ANALYSIS_METHODS.includes(form.method as AnalysisMethod)) {
    return 'Method must be STPA, CAST, or GRC.'
  }
  return null
}

/** Build the request body, dropping the anchor when empty (it is optional). */
export function newAnalysisBody(form: NewAnalysisForm): Record<string, string> {
  const body: Record<string, string> = {
    name: form.name.trim(),
    method: form.method,
    tlp: form.tlp,
  }
  const anchor = form.architecture_anchor_id.trim()
  if (anchor) body['architecture_anchor_id'] = anchor
  return body
}

/** Node-list URL scoped to an analysis (or the unscoped list when null), in a requested order.
 *
 * The order is a request parameter rather than a client-side re-rank because the store resolves
 * it before the exposure filter runs — which is what keeps ordering from affecting what a
 * reader is allowed to see. */
export function nodesUrlForAnalysis(
  analysisId: string | null,
  sort?: string,
  order?: 'asc' | 'desc',
): string {
  const params = new URLSearchParams()
  if (analysisId) params.set('analysis_id', analysisId)
  if (sort) params.set('sort', sort)
  if (order) params.set('order', order)
  const query = params.toString()
  return query ? `/api/assurance/nodes?${query}` : '/api/assurance/nodes'
}

/** The selected analysis summary, or null when nothing is selected / not found. */
export function findAnalysis(
  analyses: AnalysisSummary[],
  analysisId: string | null,
): AnalysisSummary | null {
  if (!analysisId) return null
  return analyses.find((a) => a.analysis_id === analysisId) ?? null
}

/** Human message from a failed analysis mutation response body. */
export function analysisErrorMessage(body: Record<string, unknown>, status: number): string {
  if (typeof body['message'] === 'string') return body['message']
  return `HTTP ${status}`
}
