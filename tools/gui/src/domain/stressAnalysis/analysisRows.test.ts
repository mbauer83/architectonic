import { describe, expect, it } from 'vitest'
import type { DocumentTableRow, DocumentTables } from '../schemas/candidates'
import {
  cell, cellIds, changeRow, componentsHitBy, endStateName, groupedByEndState, removeRow, restoreRow, rowsOf, ticksOf,
} from './analysisRows'

const row = (row_id: string, values: DocumentTableRow['values']): DocumentTableRow => ({ row_id, values, unreadable: {} })

describe('the analysis rows', () => {
  it('reads a table by name, and none where the document lacks it', () => {
    const tables: DocumentTables = {
      tables: [{ name: 'stressors', section: 'Stressors', found: true, missing_columns: [], undeclared_columns: [],
        rows: [row('S1', { stressor: 'Load' })] }],
    }
    expect(rowsOf(tables, 'stressors').map((one) => one.row_id)).toEqual(['S1'])
    expect(rowsOf(tables, 'incidence')).toEqual([])
    expect(rowsOf(null, 'stressors')).toEqual([])
  })

  it('reads a cell as text and a many-valued cell as its ids', () => {
    const adaptation = row('A1', { end_states: ['E1', 'E2'], integration: true })
    expect(cell(adaptation, 'end_states')).toBe('E1, E2')
    expect(cell(adaptation, 'integration')).toBe('true')
    expect(cell(adaptation, 'reasoning')).toBe('')
    expect(cellIds(adaptation, 'end_states')).toEqual(['E1', 'E2'])
    expect(cellIds(row('A2', { end_states: 'E3' }), 'end_states')).toEqual(['E3'])
  })

  it('names an end state by its row, and by its id where it names none or is gone', () => {
    const ends = [row('E1', { end_state: 'Stall' }), row('E2', {})]
    expect([endStateName(ends, 'E1'), endStateName(ends, 'E2'), endStateName(ends, 'E9')]).toEqual(['Stall', 'E2', 'E9'])
  })

  it('groups stressors under their end states, ungrouped first, an unknown end state ungrouped', () => {
    const stressors = [row('S1', { end_state: 'E1' }), row('S2', {}), row('S3', { end_state: 'E9' })]
    const groups = groupedByEndState(stressors, [row('E1', { end_state: 'Stall' }), row('E2', { end_state: 'Drift' })])
    expect(groups.map((group) => [group.endState?.row_id ?? null, group.stressors.map((one) => one.row_id)]))
      .toEqual([[null, ['S2', 'S3']], ['E1', ['S1']], ['E2', []]])
  })

  it('reads ticks, skipping a row that names no stressor or component, and the components hit', () => {
    const ticks = ticksOf([
      row('I1', { stressor: 'S1', component: 'A', note: 'why' }), row('I2', { stressor: 'S2', component: 'A' }),
      row('I3', { stressor: 'S2', component: 'B' }), row('I4', { stressor: 'S1' }),
    ])
    expect(ticks.map((tick) => tick.row.row_id)).toEqual(['I1', 'I2', 'I3'])
    expect(ticks[0].note).toBe('why')
    expect(componentsHitBy(ticks, new Set(['S1', 'S2']))).toEqual(['A', 'B'])
    expect(componentsHitBy(ticks, new Set(['S1']))).toEqual(['A'])
  })

  it('states an edit against the row as it was read, and an undo as the row added back', () => {
    const read = row('S1', { stressor: 'Load', set: 'design' })
    expect(changeRow(read, { kind: 'scale' })).toEqual({ op: 'change', row_id: 'S1', based_on: read.values, cells: { kind: 'scale' } })
    expect(removeRow(read)).toEqual({ op: 'remove', row_id: 'S1', based_on: read.values })
    expect(restoreRow(read)).toEqual({ op: 'add', cells: read.values })
  })
})
