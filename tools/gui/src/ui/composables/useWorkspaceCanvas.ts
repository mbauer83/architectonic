/**
 * What the stress-analysis workspace's canvas shows, marks and does with a press, for the tab open on
 * the left. The Naive architecture and Adaptations tabs read the selected candidate against its base;
 * Stressors and End states read the naive architecture as it composes (owner, 2026-11-22: stressors
 * apply to the naive, not the model beneath it), marked with what the focus hits. A press on the
 * picture ticks or unticks it for the stressor in focus; with none in focus it selects the element,
 * which marks the stressor rows that tick it and, on a candidate tab, its row in the operations.
 */
import { computed, type Ref } from 'vue'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import { stableEntityId } from '../../domain/artifactId'
import type { Marks } from '../../domain/candidates/elementMarks'
import { diffMarks, framedMarks } from '../../domain/candidates/elementMarks'
import type { WorkspaceTab } from '../../domain/stressAnalysis/analysisProgress'
import { cell } from '../../domain/stressAnalysis/analysisRows'
import { INTEGRATION, NAIVE } from '../../domain/stressAnalysis/testSet'
import { type CanvasReading, canvasCaption, emptyCaption } from '../../domain/stressAnalysis/canvasCaption'
import { hitMarks, stressorsTicking } from '../../domain/stressAnalysis/workspaceMarks'
import type { AnalysisEdits } from './useAnalysisEdits'
import type { Candidates } from './useCandidates'
import { type ComposedDrawing, type ComposedDrawingAccess, useComposedDrawing } from './useComposedDrawing'
import type { StressAnalysis } from './useStressAnalysis'

export interface WorkspaceFocus {
  readonly tab: Ref<WorkspaceTab>
  /** The stressor row in focus on the Stressors tab. */
  readonly selected: Ref<string | null>
  /** The end state in focus on the End states tab. */
  readonly endStateFocus: Ref<string | null>
  /** The element selected on the canvas, or the one a row or a hint is about, by stable id. */
  readonly framed: Ref<string | null>
  /** The architecture judged against the test set, if any: `naive` or a candidate's id. */
  readonly judging: Ref<string | null>
  /** The candidate being judged, when it is read against the naive; null for the naive. */
  readonly judgedCandidate: Ref<string | null>
}

/** The picture the canvas shows, and whether it is still being drawn as its candidate composes. */
interface Shown {
  readonly drawing: LayoutGeometry | null
  readonly composing: boolean
}

export function useWorkspaceCanvas(
  svc: ComposedDrawingAccess, analysis: StressAnalysis, candidates: Candidates,
  edits: AnalysisEdits, focus: WorkspaceFocus,
) {
  const { tab, selected, endStateFocus, framed, judging, judgedCandidate } = focus
  /** Whether the canvas reads the selected candidate's comparison: on a candidate tab, or judging a candidate. */
  const readsCandidate = computed(() => (judging.value
    ? judging.value !== NAIVE && judging.value !== INTEGRATION
    : tab.value === 'naive' || tab.value === 'adaptations'))

  const naiveDrawn = useComposedDrawing(svc, () => analysis.naive.value)
  const candidateDrawn = useComposedDrawing(svc, () => candidates.comparison.value)
  // The integration is in the model: it is drawn as the model draws it, without the naive's own changes.
  // A candidate being judged is drawn once its comparison is read, never the naive in its place meanwhile.
  const of = (one: ComposedDrawing): Shown => ({ drawing: one.drawing.value, composing: one.composing.value })
  const shown = computed((): Shown => {
    const served = analysis.naive.value?.drawing
    if (judging.value === INTEGRATION) return served ? { drawing: served, composing: false } : of(naiveDrawn)
    if (judging.value && readsCandidate.value) {
      return judgedCandidate.value ? of(candidateDrawn) : { drawing: null, composing: false }
    }
    return readsCandidate.value && candidateDrawn.drawing.value ? of(candidateDrawn) : of(naiveDrawn)
  })
  const drawing = computed(() => shown.value.drawing)
  /** Whether the picture shown is still being drawn as its candidate composes. */
  const composing = computed(() => shown.value.composing)

  const hitsOf = (stressors: readonly string[]): ReadonlyMap<string, readonly string[]> =>
    new Map(stressors.map((id) => [id, analysis.hitsOf(id)]))
  /** The stressor rows that tick the element selected on the canvas, while no row is in focus. */
  const ticking = computed(() => stressorsTicking(analysis.ticks.value, selected.value ? null : framed.value))

  const marks = computed((): Marks => {
    const around = framed.value ? framedMarks([framed.value], 'The row, hint or element selected') : new Map()
    if (readsCandidate.value) return new Map([...diffMarks(candidates.comparison.value), ...around])
    if (judging.value) return around
    if (tab.value === 'stressors' && selected.value) {
      return new Map([...hitMarks(hitsOf([selected.value])), ...around])
    }
    if (tab.value === 'end-states' && endStateFocus.value) {
      const under = analysis.stressors.value.filter((row) => cell(row, 'end_state') === endStateFocus.value)
      return hitMarks(hitsOf(under.map((row) => row.row_id)))
    }
    return around
  })

  /** What the canvas shows, as its caption reads it. */
  const reading = computed((): CanvasReading => ({
    tab: tab.value, selected: selected.value, judging: judging.value,
    judgedName: candidates.all.value.find((one) => one.id === judging.value)?.name ?? judging.value ?? '',
    judgedRead: judgedCandidate.value !== null,
  }))
  const hint = computed(() => canvasCaption(reading.value))
  const emptyText = computed(() => emptyCaption(reading.value))

  /** The naive architecture's own id for an element the canvas names by its stable id. */
  const fullIdOf = (stableId: string): string =>
    analysis.naive.value?.view.entities.find((one) => stableEntityId(one.id) === stableId)?.id ?? stableId

  /** A press on the picture: ticks or unticks it for the stressor in focus, otherwise selects it. */
  const pick = (stableId: string) => {
    const stressor = selected.value
    if (tab.value !== 'stressors' || !stressor || judging.value) {
      framed.value = framed.value === stableId ? null : stableId
      return
    }
    const tick = analysis.ticks.value.find(
      (one) => one.stressor === stressor && stableEntityId(one.component) === stableId,
    )
    void (tick ? edits.untick(tick) : edits.tick(stressor, fullIdOf(stableId)))
  }

  return { readsCandidate, drawing, composing, marks, hint, emptyText, ticking, pick }
}
