/**
 * Pure helpers for the ephemeral viewpoint-execution matrix: axis resolution for both axis
 * modes, the bridging-invariant cell population, and the `cell_emphasis` style lookup.
 * Never persisted, no `ViewpointApplication` — this is a read-only representation of a
 * `EvaluateViewpoint` result.
 */

import { matrixAxisMode } from '../../domain/viewpointPresentation'
import type { PresentationNode } from '../../domain/viewpointPresentation'
import type { ConnectionItemSummary, ProjectedOccurrence, ViewpointExecutionResult, ViewpointProjection } from '../../domain'
import type { StyleValue } from '../../domain/schemas/viewpoints'

/** Same shape as `EntitiesView.helpers.ts`'s function of the same name — kept as a small
 * local duplicate rather than a cross-view import. */
export const projectionByItemId = (projection: ViewpointProjection | null): ReadonlyMap<string, ProjectedOccurrence> =>
  new Map((projection?.items ?? []).map((item) => [item.item_id, item]))

export interface MatrixAxes {
  readonly rowIds: readonly string[]
  readonly columnIds: readonly string[]
}

/** Grouped mode: one population on both axes — the existing symmetric matrix builder's
 * behavior; `row_by`/`column_by` are a display-only row/column grouping, not a different
 * axis population. Criteria mode: the two independent, possibly-disjoint populations the
 * execution result already computed (`matrix_axes`). */
export const resolveMatrixAxes = (
  presentation: PresentationNode | null,
  result: ViewpointExecutionResult | null,
): MatrixAxes => {
  if (!result) return { rowIds: [], columnIds: [] }
  const mode = presentation ? matrixAxisMode(presentation) : null
  if (mode === 'criteria' && result.matrix_axes) {
    return { rowIds: result.matrix_axes.row_entity_ids, columnIds: result.matrix_axes.column_entity_ids }
  }
  return { rowIds: result.entity_ids, columnIds: result.entity_ids }
}

export interface MatrixCell {
  readonly connectionCount: number
  readonly connectionTypes: readonly string[]
}

export const cellKey = (rowId: string, columnId: string): string => `${rowId}|${columnId}`

/** Bridging invariant: a connection appears in a cell iff one endpoint is in the row set
 * and the other in the column set, in either orientation — evaluated independently per
 * orientation so a self-loop entity (source === target, both sets containing it) is not
 * double-counted into the same cell. */
export const buildMatrixCells = (
  rowIds: readonly string[],
  columnIds: readonly string[],
  connections: readonly ConnectionItemSummary[],
): ReadonlyMap<string, MatrixCell> => {
  const rowSet = new Set(rowIds)
  const columnSet = new Set(columnIds)
  const accum = new Map<string, { count: number; types: string[] }>()
  const record = (rowId: string, columnId: string, type: string): void => {
    const key = cellKey(rowId, columnId)
    const existing = accum.get(key)
    if (existing) {
      existing.count += 1
      if (!existing.types.includes(type)) existing.types.push(type)
    } else {
      accum.set(key, { count: 1, types: [type] })
    }
  }
  for (const conn of connections) {
    if (rowSet.has(conn.source) && columnSet.has(conn.target)) record(conn.source, conn.target, conn.type)
    if (conn.source !== conn.target && rowSet.has(conn.target) && columnSet.has(conn.source)) {
      record(conn.target, conn.source, conn.type)
    }
  }
  const cells = new Map<string, MatrixCell>()
  for (const [key, value] of accum) cells.set(key, { connectionCount: value.count, connectionTypes: [...value.types].sort() })
  return cells
}

/** `cell_emphasis` styling rules match entities, not connections (unlike `edge_*`), so a
 * cell's style is the row entity's own token, falling back to the column entity's. */
export const cellEmphasisToken = (
  rowId: string,
  columnId: string,
  entityStyleById: ReadonlyMap<string, ProjectedOccurrence>,
): StyleValue | undefined =>
  entityStyleById.get(rowId)?.style.cell_emphasis ?? entityStyleById.get(columnId)?.style.cell_emphasis
