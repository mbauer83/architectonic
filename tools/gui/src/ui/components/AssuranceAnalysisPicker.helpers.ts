// Pure helpers for the assurance analysis picker — unit-testable without a DOM.

// The methods and statuses an analysis may have, from the decoder that is checked against the
// backend's published vocabulary rather than restated here. This module held its own copy with a
// comment asking a test to keep the two equal — and a method missing from that copy cannot be picked
// or filtered for, which is how FMEA analyses became unreachable from the matrix page.
import { Schema } from 'effect'
import {
  ANALYSIS_METHODS,
  ANALYSIS_STATUSES,
  AssuranceAnalysisListSchema,
  type AnalysisMethod,
  type AnalysisStatus,
  type AssuranceAnalysisRecord,
} from '../../domain/schemas/assurance-analyses'

export { ANALYSIS_METHODS, ANALYSIS_STATUSES, type AnalysisMethod, type AnalysisStatus }

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

/** One analysis as the picker needs it — the decoded record, not a looser restatement of it.
 *
 * It was an interface of its own declaring `status`, `tlp` and `architecture_anchor_id` optional, for
 * a route that has always sent all three. A decoder more permissive than the server turns a genuinely
 * missing field into a silently absent one, which is the direction that costs a rendered row. */
export type AnalysisSummary = AssuranceAnalysisRecord

export interface AnalysisOption {
  value: string
  label: string
}

/** The analyses out of a `GET /api/assurance/analyses` body, decoded rather than cast.
 *
 * The picker asserted `as { analyses: AnalysisSummary[] }` over `resp.json()`, which checks nothing
 * and named a looser shape than the route sends. Here rather than in the component so it is unit-
 * testable without a DOM, like everything else in this module. Throws on a body that does not match
 * the contract — the caller already reports a failed load, and a silently mis-decoded list renders as
 * an empty picker with nothing said. */
export function decodeAnalysisList(body: unknown): AnalysisSummary[] {
  return [...Schema.decodeUnknownSync(AssuranceAnalysisListSchema)(body).analyses]
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
