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
import type { DocumentDetail } from '../../domain'
import type {
  AnalysisIncidence, AnalysisProgress, CandidateComparison, DocumentTables,
} from '../../domain/schemas/candidates'
import type { AnalysisEvaluation } from '../../domain/schemas/stressEvaluation'
import type { TableName, TableRowEdit } from '../../domain/stressAnalysis/analysisRows'
import { rowsOf, ticksOf } from '../../domain/stressAnalysis/analysisRows'
import { heldApartIds } from '../../domain/stressAnalysis/testSet'
import { stableEntityId } from '../../domain/artifactId'
import { UNNAMED_YET } from '../../domain/candidates/candidateComparison'
import { formatEffectError, isConflict } from '../lib/errors'


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

  /**
   * An element of the naive architecture by name, written by its reference or, for one the naive creates, by the
   * id chosen for it; an unknown one as it is. Until the naive is read, an element is not called by its id.
   */
  const names = computed(() => new Map((naive.value?.view.entities ?? []).flatMap((entity) => {
    const name = typeof entity.fields.name === 'string' ? entity.fields.name : entity.id
    const spellings = [entity.id, ...(entity.artifact_id ? [entity.artifact_id] : [])]
    return spellings.map((id) => [stableEntityId(id), name] as const)
  })))
  const nameOf = (id: string): string => names.value.get(stableEntityId(id)) ?? (naive.value ? id : UNNAMED_YET)

  /** What the incidence read derived for a stressor: the components it hits, and those the naive lacks. */
  const derived = computed(() => new Map((incidence.value?.stressors ?? []).map((row) => [String(row.id), row])))
  const idsIn = (value: unknown): readonly string[] => (Array.isArray(value) ? value.map(String) : [])
  const hitsOf = (stressor: string): readonly string[] => idsIn(derived.value.get(stressor)?.hits)
  const missingOf = (stressor: string): readonly string[] => idsIn(derived.value.get(stressor)?.missing_elements)

  /** Read the document and everything derived from it; a failure to read is thrown. */
  const read = async (): Promise<void> => {
    const id = documentId()
    document.value = await Effect.runPromise(svc.getDocument(id))
    const [held, grid, left, judged, composed] = await Promise.all([
      Effect.runPromise(svc.readDocumentTables(id)),
      Effect.runPromise(svc.readAnalysisIncidence(id)),
      Effect.runPromise(svc.readAnalysisProgress(id)),
      Effect.runPromise(svc.readTestSet(id)),
      naiveId.value
        ? Effect.runPromise(svc.compareCandidate(naiveId.value, 'model'))
        : Promise.resolve(null),
    ])
    tables.value = held
    incidence.value = grid
    progress.value = left
    evaluation.value = judged
    naive.value = composed
  }

  /** Read the analysis again after a write, leaving a refusal already said where it is. */
  const refresh = async (): Promise<void> => {
    try {
      await read()
    } catch (failure) {
      error.value = formatEffectError(failure)
    }
  }

  const reload = async (): Promise<void> => {
    loading.value = true
    try {
      await read()
      error.value = null
    } catch (failure) {
      error.value = formatEffectError(failure)
    } finally {
      loading.value = false
    }
  }

  /** The writes asked for and not yet answered, run one at a time in the order they were asked. */
  let queue: Promise<unknown> = Promise.resolve()
  let waiting = 0

  /**
   * Write *rows* to *table*, then — when no other write is waiting — read the analysis again: a run of
   * writes is read back once, after its last. Answers the ids of added rows, or null when the write
   * was refused — a stale row says so and the analysis is read again at once.
   */
  const write = async (table: TableName, rows: readonly TableRowEdit[]): Promise<readonly string[] | null> => {
    try {
      const written = await Effect.runPromise(svc.editDocumentTable(documentId(), table, rows))
      if (waiting === 1) await refresh()
      return written.added_row_ids
    } catch (failure) {
      if (isConflict(failure)) await refresh()
      error.value = isConflict(failure)
        ? 'That row changed since it was read. It has been read again; make the edit on what it holds now.'
        : formatEffectError(failure)
      return null
    }
  }

  /**
   * Queue a write of *rows* to *table*: it runs once every write asked for before it has been answered,
   * so a line kept while another is being written is written after it, never dropped and never sent
   * alongside it. A refusal stays said until a new run of writes begins.
   */
  const edit = (table: TableName, rows: readonly TableRowEdit[]): Promise<readonly string[] | null> => {
    if (waiting === 0) error.value = null
    waiting += 1
    saving.value = true
    const turn = queue.then(() => write(table, rows))
    queue = turn
    return turn.finally(() => {
      waiting -= 1
      saving.value = waiting > 0
    })
  }

  const allStressors = computed(() => rowsOf(tables.value, 'stressors'))
  const heldApart = computed(() => heldApartIds(evaluation.value))
  const testStressors = computed(() => allStressors.value.filter((row) => heldApart.value.has(row.row_id)))

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
