import { Effect } from 'effect'
import {
  AnalysisIncidenceSchema, AnalysisProgressSchema, AnalysisStartedSchema, CandidateApplicationSchema,
  CandidateComparisonSchema,
  CandidateListSchema,
  CandidateResponseSchema, DocumentTablesSchema, DocumentTableWriteSchema, IntegrationCheckSchema,
} from '../../domain/schemas/candidates'
import {
  AnalysisEvaluationSchema, CandidateResidualitySchema, HeldOutSchema, StressPerspectivesSchema,
} from '../../domain/schemas/stressEvaluation'
import { encodeIdentitySegment } from '../../domain/identitySegments'
import type { StressAnalysisRepository } from '../../ports/StressAnalysisRepository'
import { buildUrl, deleteNoContent, fetchJson, patchJson, postJson } from './httpTransport'

const candidateUrl = (id: string, part = '', query?: Record<string, string | undefined>): string =>
  buildUrl(`/change-sets/${encodeIdentitySegment(id)}${part}`, query)
const documentUrl = (id: string, part: string): string => buildUrl(`/documents/${encodeIdentitySegment(id)}${part}`)

/** The stress-analysis workspace's half of the HTTP adapter. */
export const stressAnalysisMethods = (): StressAnalysisRepository => ({
  listCandidates: () => fetchJson(buildUrl('/change-sets'), CandidateListSchema)
    .pipe(Effect.map((envelope) => envelope.candidates)),
  createCandidate: (record, diagram) =>
    postJson(buildUrl('/change-sets'), { record, ...(diagram ? { diagram } : {}) }, CandidateResponseSchema),
  startAnalysis: (start) => postJson(buildUrl('/stress-analyses'), start, AnalysisStartedSchema),
  deleteCandidate: (id) => deleteNoContent(candidateUrl(id, '', { dry_run: 'false' })),
  rebaseCandidate: (id, basedOn) =>
    postJson(candidateUrl(id, '/rebase'), { based_on: basedOn }, CandidateResponseSchema),
  applyCandidate: (id, dryRun) =>
    postJson(candidateUrl(id, '/apply'), { dry_run: dryRun }, CandidateApplicationSchema),
  readCandidate: (id) => fetchJson(candidateUrl(id), CandidateResponseSchema),
  editCandidate: (id, basedOn, patch) =>
    patchJson(candidateUrl(id), { based_on: basedOn, patch }, CandidateResponseSchema),
  recordOperation: (id, basedOn, operation) =>
    postJson(candidateUrl(id, '/operations'), { based_on: basedOn, operations: [operation] }, CandidateResponseSchema),
  compareCandidate: (id, base, diagram) =>
    fetchJson(candidateUrl(id, '/diff', { base, diagram }), CandidateComparisonSchema),
  checkCandidates: (ids) => postJson(buildUrl('/change-set-checks'), { candidates: ids }, IntegrationCheckSchema),
  readDocumentTables: (documentId) => fetchJson(documentUrl(documentId, '/tables'), DocumentTablesSchema),
  editDocumentTable: (documentId, table, rows) => patchJson(
    documentUrl(documentId, `/tables/${encodeIdentitySegment(table)}`), { rows, dry_run: false },
    DocumentTableWriteSchema,
  ),
  readAnalysisProgress: (documentId) => fetchJson(documentUrl(documentId, '/progress'), AnalysisProgressSchema),
  readAnalysisIncidence: (documentId) => fetchJson(documentUrl(documentId, '/incidence'), AnalysisIncidenceSchema),
  readTestSet: (documentId) => fetchJson(documentUrl(documentId, '/test-set'), AnalysisEvaluationSchema),
  holdOutTestSet: (documentId, seed) => postJson(
    documentUrl(documentId, '/test-set/hold-out'), { ...(seed === undefined ? {} : { seed }), dry_run: false },
    HeldOutSchema,
  ),
  readResiduality: (candidateId) => fetchJson(candidateUrl(candidateId, '/residuality'), CandidateResidualitySchema),
  listStressPerspectives: () => fetchJson(buildUrl('/stress-perspectives'), StressPerspectivesSchema),
})
