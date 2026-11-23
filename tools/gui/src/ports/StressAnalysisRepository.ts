import type { Effect } from 'effect'
import type {
  AnalysisIncidence, AnalysisProgress, CandidateComparison, CandidateResponse, CandidateSummary,
  DocumentTables, DocumentTableWrite, IntegrationCheck,
} from '../domain/schemas/candidates'
import type { RepoError } from './repositoryErrors'
import type { TableRowEdit } from '../domain/stressAnalysis/analysisRows'

/**
 * The stress-analysis workspace's surface: candidate architectures, the analysis document's typed
 * tables, and the progress and incidence the server derives from both. Every write goes through the
 * backend's write queue; a stale `based_on` answers 409 and the caller reads again.
 */
export interface StressAnalysisRepository {
  readonly listCandidates: () => Effect.Effect<readonly CandidateSummary[], RepoError>
  readonly createCandidate: (
    record: Readonly<Record<string, unknown>>, diagram?: string,
  ) => Effect.Effect<CandidateResponse, RepoError>
  readonly readCandidate: (id: string) => Effect.Effect<CandidateResponse, RepoError>
  readonly editCandidate: (
    id: string, basedOn: string, patch: Readonly<Record<string, unknown>>,
  ) => Effect.Effect<CandidateResponse, RepoError>
  /** *base* is `model` or another candidate's id; *diagram* adds that stored diagram's drawing. */
  readonly compareCandidate: (
    id: string, base: string, diagram?: string,
  ) => Effect.Effect<CandidateComparison, RepoError>
  /** Overlaps between the offered candidates (state `candidate`); structural, never a merge. */
  readonly checkCandidates: (ids: readonly string[]) => Effect.Effect<IntegrationCheck, RepoError>
  readonly readDocumentTables: (documentId: string) => Effect.Effect<DocumentTables, RepoError>
  readonly editDocumentTable: (
    documentId: string, table: string, rows: readonly TableRowEdit[],
  ) => Effect.Effect<DocumentTableWrite, RepoError>
  readonly readAnalysisProgress: (documentId: string) => Effect.Effect<AnalysisProgress, RepoError>
  readonly readAnalysisIncidence: (documentId: string) => Effect.Effect<AnalysisIncidence, RepoError>
}
