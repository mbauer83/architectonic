/**
 * The workspace's row edits, in its words: add, change and remove a stressor (with *Undo*), put it
 * under an end state or create one by naming it, say why an end state needs no change, and tick, untick
 * and annotate what it hits. Each is
 * one row batch through `StressAnalysis.edit`, stated against the row as it was read.
 */
import type { DocumentTableRow } from '../../domain/schemas/candidates'
import type { Tick } from '../../domain/stressAnalysis/analysisRows'
import { changeRow, removeRow, restoreRow } from '../../domain/stressAnalysis/analysisRows'
import type { ShowToast } from '../keys'
import type { StressAnalysis } from './useStressAnalysis'

/** A new stressor is a design stressor until said otherwise: `set` is required by the document type. */
const NEW_STRESSOR = { set: 'design' }

export function useAnalysisEdits(analysis: StressAnalysis, toast: ShowToast) {
  const addStressor = async (cells: Readonly<Record<string, string>> = {}): Promise<string | null> =>
    (await analysis.edit('stressors', [{ op: 'add', cells: { ...NEW_STRESSOR, ...cells } }]))?.[0] ?? null

  const changeStressor = (row: DocumentTableRow, cells: Readonly<Record<string, string>>) =>
    analysis.edit('stressors', [changeRow(row, cells)])

  /** Remove a stressor and its ticks; *Undo* in the toast adds them back. */
  const removeStressor = async (row: DocumentTableRow) => {
    const ticks = analysis.ticks.value.filter((tick) => tick.stressor === row.row_id).map((tick) => tick.row)
    if (ticks.length && !(await analysis.edit('incidence', ticks.map(removeRow)))) return
    if (!(await analysis.edit('stressors', [removeRow(row)]))) return
    toast(`Removed ${row.row_id}.`, 'info', 8000, {
      label: 'Undo',
      run: () => { void restore(row, ticks) },
    })
  }
  const restore = async (row: DocumentTableRow, ticks: readonly DocumentTableRow[]) => {
    const added = await analysis.edit('stressors', [restoreRow(row)])
    const id = added?.[0]
    if (id && ticks.length) {
      await analysis.edit('incidence', ticks.map((tick) => ({ op: 'add', cells: { ...tick.values, stressor: id } })))
    }
  }

  const setEndState = (row: DocumentTableRow, endState: string) => changeStressor(row, { end_state: endState })

  /** Name a new end state and put *row* under it. */
  const createEndStateFor = async (row: DocumentTableRow, name: string) => {
    const created = await analysis.edit('end-states', [{ op: 'add', cells: { end_state: name } }])
    const id = created?.[0]
    if (!id) return
    const current = analysis.stressors.value.find((one) => one.row_id === row.row_id)
    if (current) await setEndState(current, id)
  }

  /** An end state answered by no change, for the reason given; an empty reason takes the answer back. */
  const answerNoChange = (endState: DocumentTableRow, reason: string) =>
    analysis.edit('end-states', [changeRow(endState, { no_change_reason: reason })])

  const tick = (stressor: string, component: string) =>
    analysis.edit('incidence', [{ op: 'add', cells: { stressor, component } }])
  const untick = (one: Tick) => analysis.edit('incidence', [removeRow(one.row)])
  const note = (one: Tick, text: string) => analysis.edit('incidence', [changeRow(one.row, { note: text })])

  return {
    addStressor, changeStressor, removeStressor, setEndState, createEndStateFor, answerNoChange, tick, untick, note,
  }
}

export type AnalysisEdits = ReturnType<typeof useAnalysisEdits>
