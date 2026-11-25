/**
 * The test set in the workspace's words: which rows are held apart, a verdict written as a row of the
 * survival table, the residuality line an architecture is summed up by, and the procedure's order.
 * The figures themselves are the server's; nothing here computes a coefficient.
 */
import type { DocumentTableRow } from '../schemas/candidates'
import type { AnalysisEvaluation, ArchitectureStanding, Verdict } from '../schemas/stressEvaluation'
import type { TableRowEdit } from './analysisRows'
import { cell, changeRow } from './analysisRows'

/** How a verdict names the naive architecture; any other is named by its candidate id. */
export const NAIVE = 'naive'

/** Whether a stressor row is held apart in the test set. A row naming no set is a design stressor. */
export const inTestSet = (row: DocumentTableRow): boolean => cell(row, 'set') === 'test'

/** The survival row holding *architecture*'s verdict on *stressor*: the last, as a later one replaces it. */
export const verdictRow = (
  rows: readonly DocumentTableRow[], stressor: string, architecture: string,
): DocumentTableRow | undefined =>
  rows.filter((row) => cell(row, 'stressor') === stressor && cell(row, 'architecture') === architecture).at(-1)

/** A judgement written: the existing row changed, or a new one added. */
export const judgement = (
  existing: DocumentTableRow | undefined, stressor: string, architecture: string,
  cells: Readonly<{ verdict?: Verdict; usable?: boolean; reasoning?: string }>,
): TableRowEdit => existing
  ? changeRow(existing, cells)
  : { op: 'add', cells: { stressor, architecture, usable: true, ...cells } }

/** A signed figure to two places: +0.33, −0.08, ±0.00. */
export const signed = (value: number): string =>
  `${value > 0 ? '+' : value < 0 ? '−' : '±'}${Math.abs(value).toFixed(2)}`

/** "Residuality +0.33 · survives 8 of 12 (naive 4)", or how many are judged while some are not. */
export const residualityLine = (standing: ArchitectureStanding): string => {
  const survives = `survives ${standing.survives} of ${standing.usable}`
  if (standing.architecture === NAIVE) {
    return standing.judged < standing.usable ? `${standing.judged} of ${standing.usable} judged` : survives
  }
  return standing.residuality === undefined
    ? `${standing.judged} of ${standing.usable} judged`
    : `Residuality ${signed(standing.residuality)} · ${survives} (naive ${standing.naive_survives})`
}

/** The hover of a line: the strict figure, and what the degraded verdicts did to it. */
export const residualityDetail = (standing: ArchitectureStanding): string => [
  ...(standing.strict === undefined ? [] : [`Strict ${signed(standing.strict)}, counting full survivals only.`]),
  `Survives ${standing.survives}, degrades ${standing.degrades}, fails ${standing.fails}`
    + ` of ${standing.usable} usable test stressors; a degraded verdict counts one half.`,
].join(' ')

/** One step of the procedure, in its order; shown as progress, never as a gate. */
export interface ProcedureStep {
  readonly label: string
  readonly done: boolean
}

export const procedure = (stage: AnalysisEvaluation['stage']): readonly ProcedureStep[] => [
  { label: 'Judge the naive', done: stage.naive_judged },
  { label: 'Adapt', done: stage.adapted },
  { label: 'Integrate', done: stage.integrated },
  { label: 'Judge the integration', done: stage.integration_judged },
]
