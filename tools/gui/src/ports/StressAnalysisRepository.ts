import type { Effect } from 'effect'
import type {
  AnalysisIncidence, AnalysisProgress, AnalysisStarted, CandidateApplication, CandidateComparison, CandidateDiagramSaved,
  CandidateResponse,
  CandidateSummary,
  DocumentTables, DocumentTableWrite, IntegrationCheck,
} from '../domain/schemas/candidates'
import type {
  AnalysisEvaluation, CandidateResiduality, HeldOut, StressPerspectives,
} from '../domain/schemas/stressEvaluation'
import type { LayoutGeometry } from '../domain/schemas/diagramLayoutGeometry'
import type { RepoError } from './repositoryErrors'
import type { TableRowEdit } from '../domain/stressAnalysis/analysisRows'

/**
 * The stress-analysis workspace's surface: candidate architectures, the analysis document's typed
 * tables, and the progress and incidence the server derives from both. Every write goes through the
 * backend's write queue; a stale `based_on` answers 409 and the caller reads again.
 */
export interface StressAnalysisRepository {
  readonly listCandidates: () => Effect.Effect<readonly CandidateSummary[], RepoError>
  /** A new candidate from its header; one naming a `diagram` and no `scope` is scoped by what it draws. */
  readonly createCandidate: (record: Readonly<Record<string, unknown>>) => Effect.Effect<CandidateResponse, RepoError>
  /**
   * Start an analysis in one write: the architecture under evaluation, its naive candidate (*naive*: its
   * name, and its scope, the diagram it is drawn on, or the candidate it stacks on), and the document
   * naming it with the optional *context*. A refusal leaves neither.
   */
  readonly startAnalysis: (start: {
    readonly title: string; readonly context?: string; readonly naive: Readonly<Record<string, unknown>>
  }) => Effect.Effect<AnalysisStarted, RepoError>
  /** A view generated from a scope no stored diagram draws: its entities and the relations among them. */
  readonly drawScope: (scope: readonly string[], name: string) => Effect.Effect<LayoutGeometry, RepoError>
  /** Delete a candidate; refused (409, saying why) while one stacks on it or an analysis starts from it. */
  readonly deleteCandidate: (id: string) => Effect.Effect<void, RepoError>
  /** Write each drifted operation again against the model as it stands now, keeping what it asks for. */
  readonly rebaseCandidate: (id: string, basedOn: string) => Effect.Effect<CandidateResponse, RepoError>
  /**
   * Write the candidate's operations onto the model in one write, all or none, and integrate it. A dry
   * run answers what would be written and the refusal; a refused apply answers 409, saying why.
   */
  readonly applyCandidate: (id: string, dryRun: boolean) => Effect.Effect<CandidateApplication, RepoError>
  /**
   * Save the view generated from the scope of a candidate drawn on no stored diagram as a new diagram, and
   * draw the candidate on it; *name* defaults to the candidate's. Writes nothing of the candidate's operations.
   */
  readonly saveCandidateDiagram: (
    id: string, basedOn: string, name?: string,
  ) => Effect.Effect<CandidateDiagramSaved, RepoError>
  readonly readCandidate: (id: string) => Effect.Effect<CandidateResponse, RepoError>
  readonly editCandidate: (
    id: string, basedOn: string, patch: Readonly<Record<string, unknown>>,
  ) => Effect.Effect<CandidateResponse, RepoError>
  /** Record an edit among the candidate's operations; the server reads its base and merges it per claim. */
  readonly recordOperation: (
    id: string, basedOn: string, operation: Readonly<Record<string, unknown>>,
  ) => Effect.Effect<CandidateResponse, RepoError>
  /**
   * *base* is `model` or another candidate's id. The drawing is *diagram*'s where given, else the one the
   * candidate's stack is drawn on, else a view generated from its scope.
   */
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
  /** The test set, its verdicts, and each judged or integrated architecture's residuality. */
  readonly readTestSet: (documentId: string) => Effect.Effect<AnalysisEvaluation, RepoError>
  /** Move a random third of the design stressors into the test set; the seed drawn with is answered. */
  readonly holdOutTestSet: (documentId: string, seed?: number) => Effect.Effect<HeldOut, RepoError>
  /** A candidate's residuality in each analysis that judged it. */
  readonly readResiduality: (candidateId: string) => Effect.Effect<CandidateResiduality, RepoError>
  /** The perspectives offered to whoever writes stressors. */
  readonly listStressPerspectives: () => Effect.Effect<StressPerspectives, RepoError>
}
