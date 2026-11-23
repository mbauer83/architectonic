/**
 * One stress analysis as the workspace holds it: the document, its typed tables, the incidence and
 * progress the server derives from them, and the naive architecture composed over its scope.
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
import type { TableName, TableRowEdit } from '../../domain/stressAnalysis/analysisRows'
import { rowsOf, ticksOf } from '../../domain/stressAnalysis/analysisRows'
import { formatEffectError } from '../lib/errors'

const isConflict = (failure: unknown): boolean =>
  typeof failure === 'object' && failure !== null && 'status' in failure && failure.status === 409

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
  /** The naive architecture composed over the model, with the scope diagram's drawing. */
  const naive = shallowRef<CandidateComparison | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  const naiveId = computed(() => frontmatter(document.value, 'naive-candidate'))
  const scopeDiagram = computed(() => frontmatter(document.value, 'scope-diagram'))
  const question = computed(() => frontmatter(document.value, 'question'))

  /** An element of the naive architecture by name; a provisional `$ref:` id or an unknown one as it is. */
  const names = computed(() => new Map((naive.value?.view.entities ?? [])
    .map((entity) => [entity.id, typeof entity.fields.name === 'string' ? entity.fields.name : entity.id])))
  const nameOf = (id: string): string => names.value.get(id) ?? id

  const reload = async (): Promise<void> => {
    const id = documentId()
    loading.value = true
    try {
      document.value = await Effect.runPromise(svc.getDocument(id))
      const [read, grid, left, composed] = await Promise.all([
        Effect.runPromise(svc.readDocumentTables(id)),
        Effect.runPromise(svc.readAnalysisIncidence(id)),
        Effect.runPromise(svc.readAnalysisProgress(id)),
        naiveId.value
          ? Effect.runPromise(svc.compareCandidate(naiveId.value, 'model', scopeDiagram.value || undefined))
          : Promise.resolve(null),
      ])
      tables.value = read
      incidence.value = grid
      progress.value = left
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

  return {
    document, tables, incidence, progress, naive, loading, saving, error,
    naiveId, scopeDiagram, question, nameOf, reload, edit,
    stressors: computed(() => rowsOf(tables.value, 'stressors')),
    endStates: computed(() => rowsOf(tables.value, 'end-states')),
    adaptations: computed(() => rowsOf(tables.value, 'adaptations')),
    /** The incidence table's rows as ticks: which stressor hits which component, and why. */
    ticks: computed(() => ticksOf(rowsOf(tables.value, 'incidence'))),
  }
}

export type StressAnalysis = ReturnType<typeof useStressAnalysis>
