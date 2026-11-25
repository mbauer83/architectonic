/**
 * What the stress-analysis workspace's canvas shows, marks and does with a press, for the tab open on
 * the left. The Naive architecture and Adaptations tabs read the selected candidate against its base;
 * Stressors and End states read the naive architecture as it composes (owner, 2026-11-22: stressors
 * apply to the naive, not the model beneath it), marked with what the focus hits. A press on the
 * picture ticks or unticks it for the stressor in focus; with none in focus it selects the element,
 * which marks the stressor rows that tick it and, on a candidate tab, its row in the operations.
 */
import { computed, type Ref } from 'vue'
import { stableEntityId } from '../../domain/artifactId'
import type { Marks } from '../../domain/candidates/canvasMarks'
import { diffMarks, framedMarks } from '../../domain/candidates/canvasMarks'
import type { WorkspaceTab } from '../../domain/stressAnalysis/analysisProgress'
import { cell } from '../../domain/stressAnalysis/analysisRows'
import { INTEGRATION } from '../../domain/stressAnalysis/testSet'
import { hitMarks, stressorsTicking } from '../../domain/stressAnalysis/workspaceMarks'
import type { AnalysisEdits } from './useAnalysisEdits'
import type { Candidates } from './useCandidates'
import { type ComposedDrawingAccess, useComposedDrawing } from './useComposedDrawing'
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

export function useWorkspaceCanvas(
  svc: ComposedDrawingAccess, analysis: StressAnalysis, candidates: Candidates,
  edits: AnalysisEdits, focus: WorkspaceFocus,
) {
  const { tab, selected, endStateFocus, framed, judging, judgedCandidate } = focus
  /** Whether the canvas reads the selected candidate's comparison: on a candidate tab, or judging a candidate. */
  const readsCandidate = computed(() => (judging.value
    ? judgedCandidate.value !== null
    : tab.value === 'naive' || tab.value === 'adaptations'))

  const naiveDrawn = useComposedDrawing(svc, () => analysis.naive.value)
  const candidateDrawn = useComposedDrawing(svc, () => candidates.comparison.value)
  // The integration is in the model: it is drawn as the model draws it, without the naive's own changes.
  const drawing = computed(() => (judging.value === INTEGRATION ? analysis.naive.value?.drawing : null)
    ?? (readsCandidate.value ? candidateDrawn.value : null) ?? naiveDrawn.value)

  const hitsOf = (stressors: readonly string[]): ReadonlyMap<string, readonly string[]> =>
    new Map(stressors.map((id) => [id, analysis.hitsOf(id)]))
  /** The stressor rows that tick the element selected on the canvas, while no row is in focus. */
  const ticking = computed(() => stressorsTicking(analysis.ticks.value, selected.value ? null : framed.value))

  const marks = computed((): Marks => {
    const around = framed.value ? framedMarks([framed.value], 'The row, hint or element selected') : new Map()
    if (readsCandidate.value) return new Map([...diffMarks(candidates.comparison.value?.diff ?? []), ...around])
    if (judging.value) return around
    if (tab.value === 'stressors' && selected.value) return new Map([...hitMarks(hitsOf([selected.value])), ...around])
    if (tab.value === 'end-states' && endStateFocus.value) {
      const under = analysis.stressors.value.filter((row) => cell(row, 'end_state') === endStateFocus.value)
      return hitMarks(hitsOf(under.map((row) => row.row_id)))
    }
    return around
  })

  const hint = computed(() => {
    if (judging.value === INTEGRATION) {
      return 'The integration is the model as the integrated candidates left it · Scroll to zoom · Drag to pan'
    }
    if (judging.value) {
      return judgedCandidate.value
        ? 'The candidate being judged, marked with what it changes from the naive · Scroll to zoom'
        : 'The naive architecture, being judged · Scroll to zoom · Drag to pan'
    }
    if (tab.value === 'stressors' && selected.value) {
      return `Press an element to tick or untick it for ${selected.value} · Scroll to zoom · Drag to pan`
    }
    return tab.value === 'stressors'
      ? 'Select a row, or an element to mark the rows that tick it · Scroll to zoom · Drag to pan'
      : 'Select a row or an element · Scroll to zoom · Drag to pan'
  })

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

  return { readsCandidate, drawing, marks, hint, ticking, pick }
}
