/**
 * What the progress read says, in the workspace's words: what is left (each a sentence that opens the
 * tab and row it is about), and the coverage hints that replaced *Suggest stressors* (F13) — gaps, not
 * suggestions, so nothing is drawn or invented here.
 */
import type { AnalysisProgress } from '../schemas/candidates'

export type WorkspaceTab = 'naive' | 'stressors' | 'end-states' | 'adaptations' | 'integration'

/** One thing left to do, and where it is. */
export interface LeftItem {
  readonly key: string
  readonly text: string
  readonly tab: WorkspaceTab
  readonly row: string
}

const TAB_OF_TABLE: Readonly<Record<string, WorkspaceTab>> = {
  stressors: 'stressors', incidence: 'stressors', 'end-states': 'end-states', adaptations: 'adaptations',
}

export const whatIsLeft = (progress: AnalysisProgress['progress']): readonly LeftItem[] => [
  ...progress.unwalked.map((row) => ({ row, tab: 'stressors' as const, text: `${row}: what happens is not written.` })),
  ...progress.without_end_state.map((row) => ({
    row, tab: 'stressors' as const, text: `${row} leads to no end state yet.`,
  })),
  ...progress.unexplained_hits.map((row) => ({
    row, tab: 'stressors' as const, text: `Tick ${row} says nothing about why.`,
  })),
  ...progress.without_required_behaviour.map((row) => ({
    row, tab: 'end-states' as const, text: `${row} names no required behaviour.`,
  })),
  ...progress.without_adaptation.map((row) => ({
    row, tab: 'end-states' as const, text: `${row} has no adaptation and no reason for none.`,
  })),
  ...progress.incomplete_rows.map(({ table, row, column }) => ({
    row, tab: TAB_OF_TABLE[table] ?? 'stressors',
    text: `${row}: ${column.replace(/_/g, ' ')} is missing or unreadable.`,
  })),
].map((item, index) => ({ ...item, key: `${index}:${item.text}` }))

/** An element no stressor touches, by how connected it is in the naive architecture. */
export interface UntouchedHint {
  readonly id: string
  readonly name: string
  readonly relations: number
}

/** The coverage hints of F13, from the scope and the rows. */
export interface CoverageHints {
  readonly wellConnected: readonly UntouchedHint[]
  readonly otherUntouched: readonly UntouchedHint[]
  readonly unusedKinds: readonly string[]
  readonly singleStressorEndStates: readonly string[]
  readonly withoutEndState: readonly string[]
}

/** Well connected: three relations or more, or in the top quarter of the untouched by relations. */
const WELL_CONNECTED = 3

export const coverageHints = (
  progress: AnalysisProgress, nameOf: (id: string) => string,
): CoverageHints => {
  const untouched = progress.coverage.untouched
    .map(({ id, fan_in, fan_out }) => ({ id, name: nameOf(id), relations: fan_in + fan_out }))
  const quarter = untouched[Math.max(0, Math.ceil(untouched.length / 4) - 1)]?.relations ?? Infinity
  const well = (hint: UntouchedHint) => hint.relations >= Math.min(WELL_CONNECTED, quarter) && hint.relations > 0
  return {
    wellConnected: untouched.filter(well),
    otherUntouched: untouched.filter((hint) => !well(hint)),
    unusedKinds: progress.coverage.unused_kinds,
    singleStressorEndStates: progress.coverage.single_stressor_end_states,
    withoutEndState: progress.progress.without_end_state,
  }
}
