/**
 * The workspace's test-set actions: a stressor written into it, a random third of the design set held
 * out into it, and a judgement — a verdict, or a stressor struck as unusable — written as a row of the
 * survival table. Each is one write, after which the analysis is read again; the residuality comes
 * back with that read and is never worked out here.
 */
import { ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { Verdict } from '../../domain/schemas/stressEvaluation'
import { cell, changeRow } from '../../domain/stressAnalysis/analysisRows'
import { judgement, verdictRow } from '../../domain/stressAnalysis/testSet'
import type { ShowToast } from '../keys'
import { formatEffectError } from '../lib/errors'
import type { StressAnalysis } from './useStressAnalysis'

export function useTestSet(
  svc: Pick<ModelService, 'holdOutTestSet'>, analysis: StressAnalysis, documentId: () => string, toast: ShowToast,
) {
  /** The architecture being judged, if any: `naive` or a candidate's id. */
  const judging = ref<string | null>(null)
  const holding = ref(false)

  const write = async (text: string, kind?: string): Promise<string | null> =>
    (await analysis.edit('stressors', [{
      op: 'add', cells: { stressor: text, set: 'test', ...(kind ? { kind } : {}) },
    }]))?.[0] ?? null

  /** Move a random third of the design stressors into the test set; says which, and the seed. */
  const holdOut = async (): Promise<void> => {
    holding.value = true
    try {
      const held = await Effect.runPromise(svc.holdOutTestSet(documentId()))
      await analysis.reload()
      toast(`Held out ${held.held_out.join(', ')} of ${held.design_stressors} design stressors (seed ${held.seed}).`)
    } catch (failure) {
      analysis.error.value = formatEffectError(failure)
    } finally {
      holding.value = false
    }
  }

  const judge = (
    stressor: string, architecture: string,
    cells: Readonly<{ verdict?: Verdict; usable?: boolean; reasoning?: string }>,
  ) => analysis.edit('survival', [
    judgement(verdictRow(analysis.verdicts.value, stressor, architecture), stressor, architecture, cells),
  ])

  /** Take a stressor back into the test set's denominator: every row that struck it says it is usable. */
  const restore = (stressor: string) => analysis.edit('survival', analysis.verdicts.value
    .filter((row) => cell(row, 'stressor') === stressor && cell(row, 'usable') === 'false')
    .map((row) => changeRow(row, { usable: true })))

  /** Judge *architecture* against the test set, or stop judging with null. */
  const judgeOn = (architecture: string | null) => { judging.value = architecture }

  return { judging, holding, write, holdOut, judge, restore, judgeOn }
}

export type TestSet = ReturnType<typeof useTestSet>
