/**
 * One stress analysis as the workspace holds it: the document, its typed tables, the incidence and
 * progress the server derives from them, the test set and its residuality, and the naive architecture
 * composed over its scope, drawn on the diagram it names or on a view generated from its scope. The
 * design reads hold the design set only; the test set is read apart.
 *
 * Every row edit goes through the document's row-batch write, stated against the row as read; where a
 * row changed since, the server answers 409, nothing is written, and the analysis is read again so the
 * next edit is made on what the row holds now.
 */
import { computed, ref, shallowRef } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import { NetworkError } from '../../domain'
import type { DocumentDetail } from '../../domain'
import type {
  AnalysisIncidence, AnalysisProgress, CandidateComparison, DocumentTables,
} from '../../domain/schemas/candidates'
import type { AnalysisEvaluation } from '../../domain/schemas/stressEvaluation'
import type { TableName, TableRowEdit } from '../../domain/stressAnalysis/analysisRows'
import { rowsOf, ticksOf } from '../../domain/stressAnalysis/analysisRows'
import { inTestSet } from '../../domain/stressAnalysis/testSet'
import { formatEffectError } from '../lib/errors'

const isConflict = (failure: unknown): boolean => failure instanceof NetworkError && failure.status === 409

/** A frontmatter value as text, empty where the document has none. */
const frontmatter = (document: DocumentDetail | null, key: string): string => {
  const value = document?.extra[key]
  return typeof value === 'string' ? value : ''
}

export function useStressAnalysis(svc: ModelService, documentId: () => string) {
  const document = shallowRef<DocumentDetail | null>(null)
  const tables = shallowRef<DocumentTables | null>(null)
  const incidence = shallowRef<AnalysisIncidence | null>(null)
  const progress = shallowRef<AnalysisProgress | null>(null)
  /** The test set, its verdicts and each judged architecture's residuality. */
  const evaluation = shallowRef<AnalysisEvaluation | null>(null)
  /** The naive architecture composed over the model, with the drawing it is read on. */
  const naive = shallowRef<CandidateComparison | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  const naiveId = computed(() => frontmatter(document.value, 'naive-candidate'))
  /** The context the evaluation is made in: the environment, and the decision it informs. */
  const context = computed(() => frontmatter(document.value, 'context'))
  /** The stored diagram the naive architecture is drawn on; empty where it is drawn as a generated view. */
  const drawnOn = computed(() => naive.value?.drawing?.artifact_id ?? '')

  /** An element of the naive architecture by name; a provisional `$ref:` id or an unknown one as it is. */
  const names = computed(() => new Map((naive.value?.view.entities ?? [])
    .map((entity) => [entity.id, typeof entity.fields.name === 'string' ? entity.fields.name : entity.id])))
  const nameOf = (id: string): string => names.value.get(id) ?? id

  /** What the incidence read derived for a stressor: the components it hits, and those the naive lacks. */
  const derived = computed(() => new Map((incidence.value?.stressors ?? []).map((row) => [String(row.id), row])))
  const idsIn = (value: unknown): readonly string[] => (Array.isArray(value) ? value.map(String) : [])
  const hitsOf = (stressor: string): readonly string[] => idsIn(derived.value.get(stressor)?.hits)
  const missingOf = (stressor: string): readonly string[] => idsIn(derived.value.get(stressor)?.missing_elements)

  const reload = async (): Promise<void> => {
    const id = documentId()
    loading.value = true
    try {
      document.value = await Effect.runPromise(svc.getDocument(id))
      const [read, grid, left, judged, composed] = await Promise.all([
        Effect.runPromise(svc.readDocumentTables(id)),
        Effect.runPromise(svc.readAnalysisIncidence(id)),
        Effect.runPromise(svc.readAnalysisProgress(id)),
        Effect.runPromise(svc.readTestSet(id)),
        naiveId.value
          ? Effect.runPromise(svc.compareCandidate(naiveId.value, 'model'))
          : Promise.resolve(null),
      ])
      tables.value = read
      incidence.value = grid
      progress.value = left
      evaluation.value = judged
      naive.value = composed
      error.value = null
    } catch (failure) {
      error.value = formatEffectError(failure)
    } finally {
      loading.value = false
    }
  }

  /**
   * Write *rows* to *table*, then read the analysis again. Answers the ids of added rows, or null when
   * the write was refused — a stale row says so and the analysis is read again.
   */
  const edit = async (table: TableName, rows: readonly TableRowEdit[]): Promise<readonly string[] | null> => {
    saving.value = true
    try {
      const written = await Effect.runPromise(svc.editDocumentTable(documentId(), table, rows))
      await reload()
      return written.added_row_ids
    } catch (failure) {
      if (isConflict(failure)) await reload()
      error.value = isConflict(failure)
        ? 'That row changed since it was read. It has been read again; make the edit on what it holds now.'
        : formatEffectError(failure)
      return null
    } finally {
      saving.value = false
    }
  }

  const allStressors = computed(() => rowsOf(tables.value, 'stressors'))
  const testStressors = computed(() => allStressors.value.filter(inTestSet))
  const heldApart = computed(() => new Set(testStressors.value.map((row) => row.row_id)))

  return {
    document, tables, incidence, progress, evaluation, naive, loading, saving, error,
    naiveId, context, drawnOn, nameOf, hitsOf, missingOf, reload, edit,
    /** The design set: every stressor the walk, the end states and the adaptations work from. */
    stressors: computed(() => allStressors.value.filter((row) => !heldApart.value.has(row.row_id))),
    /** The test set, held apart and judged at the end. */
    testStressors,
    /** The survival table's rows: each a verdict on one test stressor for one architecture. */
    verdicts: computed(() => rowsOf(tables.value, 'survival')),
    endStates: computed(() => rowsOf(tables.value, 'end-states')),
    adaptations: computed(() => rowsOf(tables.value, 'adaptations')),
    /** The design set's ticks: which stressor hits which component, and why. */
    ticks: computed(() => ticksOf(rowsOf(tables.value, 'incidence'))
      .filter((tick) => !heldApart.value.has(tick.stressor))),
  }
}

export type StressAnalysis = ReturnType<typeof useStressAnalysis>
