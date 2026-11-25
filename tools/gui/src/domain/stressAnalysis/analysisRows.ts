/**
 * The analysis document's typed tables, read as the workspace reads them: stressors grouped under
 * their end states, the ticks of the incidence table by stressor, and a row edit stated against the
 * values it was read as. The column names are the shipped stress-analysis document type's.
 */
import type { CellValue, DocumentTableRow, DocumentTables } from '../schemas/candidates'

/** One row edit of a document's typed table. `based_on` is the row's values as they were read. */
export type TableRowEdit =
  | { readonly op: 'add'; readonly cells: Readonly<Record<string, unknown>> }
  | {
      readonly op: 'change'; readonly row_id: string
      readonly based_on: Readonly<Record<string, unknown>>; readonly cells: Readonly<Record<string, unknown>>
    }
  | { readonly op: 'remove'; readonly row_id: string; readonly based_on: Readonly<Record<string, unknown>> }

export type TableName = 'stressors' | 'end-states' | 'adaptations' | 'incidence' | 'survival'

/** The rows a document holds of *name*, in its order; none where the table is not found. */
export const rowsOf = (tables: DocumentTables | null, name: TableName): readonly DocumentTableRow[] =>
  tables?.tables.find((table) => table.name === name)?.rows ?? []

const textOf = (value: CellValue | undefined): string =>
  value === undefined ? '' : Array.isArray(value) ? value.join(', ') : String(value)

/** A cell's value as text, empty where the cell is. */
export const cell = (row: DocumentTableRow, column: string): string => textOf(row.values[column])

/** An end state's name, by row id; the id where the row names none or is not there. */
export const endStateName = (endStates: readonly DocumentTableRow[], rowId: string): string => {
  const row = endStates.find((one) => one.row_id === rowId)
  return (row && cell(row, 'end_state')) || rowId
}

/** A many-valued row-reference cell as its row ids. */
export const cellIds = (row: DocumentTableRow, column: string): readonly string[] => {
  const value = row.values[column]
  return value === undefined ? [] : Array.isArray(value) ? value.map(String) : [String(value)]
}

/** One card of the End states tab: an end state (null for *Ungrouped*) and the stressors that lead to it. */
export interface EndStateGroup {
  readonly endState: DocumentTableRow | null
  readonly stressors: readonly DocumentTableRow[]
}

/** The stressors under their end states, *Ungrouped* first; an end state no stressor names still shows. */
export const groupedByEndState = (
  stressors: readonly DocumentTableRow[], endStates: readonly DocumentTableRow[],
): readonly EndStateGroup[] => {
  const known = new Set(endStates.map((row) => row.row_id))
  const ungrouped = stressors.filter((row) => !known.has(cell(row, 'end_state')))
  return [
    { endState: null, stressors: ungrouped },
    ...endStates.map((endState) => ({
      endState, stressors: stressors.filter((row) => cell(row, 'end_state') === endState.row_id),
    })),
  ]
}

/** A tick of the incidence table: the stressor hits the component, with a note on why. */
export interface Tick {
  readonly row: DocumentTableRow
  readonly stressor: string
  readonly component: string
  readonly note: string
}

export const ticksOf = (incidence: readonly DocumentTableRow[]): readonly Tick[] =>
  incidence.flatMap((row) => {
    const stressor = cell(row, 'stressor')
    const component = cell(row, 'component')
    return stressor && component ? [{ row, stressor, component, note: cell(row, 'note') }] : []
  })

/** The components the given stressors hit, each once, in the order first ticked. */
export const componentsHitBy = (ticks: readonly Tick[], stressors: ReadonlySet<string>): readonly string[] =>
  [...new Set(ticks.filter((tick) => stressors.has(tick.stressor)).map((tick) => tick.component))]

/** Change *row*'s *cells*, stated against what it was read as; an empty string clears a cell. */
export const changeRow = (row: DocumentTableRow, cells: Readonly<Record<string, unknown>>): TableRowEdit =>
  ({ op: 'change', row_id: row.row_id, based_on: row.values, cells })

export const removeRow = (row: DocumentTableRow): TableRowEdit =>
  ({ op: 'remove', row_id: row.row_id, based_on: row.values })

/** A row added back with what a removed row held, as Undo does. */
export const restoreRow = (row: DocumentTableRow): TableRowEdit => ({ op: 'add', cells: row.values })
