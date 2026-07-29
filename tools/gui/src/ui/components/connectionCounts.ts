/**
 * A row's connection degree: the total, and the directions it breaks into.
 *
 * Shared by every browse surface that lists connected things. It names no ontology, no module
 * and no field of any particular record — a caller hands over the counts it has, and gets back
 * a total and a column definition. That is deliberate: this is the third surface to want the
 * same "42 (12 / 3 / 27)" cell, and the first two had each written their own.
 *
 * The symmetric count is optional rather than defaulted to zero, and the difference matters.
 * Architecture connection types carry a `symmetric` flag from the ontology, so "no symmetric
 * relations" is a fact worth showing. Assurance edges are strictly directed with no ontology
 * behind them, so there is no such fact — printing a permanent `0` there would assert
 * something false. Absent means "the concept does not apply here", not "none".
 */

import type { DataTableColumn } from './DataTable.types'

export interface ConnectionCounts {
  in: number
  out: number
  /** Omit where the model has no notion of an undirected relation. */
  sym?: number
}

export const connectionTotal = (counts: ConnectionCounts): number =>
  counts.in + counts.out + (counts.sym ?? 0)

/** The direction breakdown, in display order — `sym` only where the model has one. */
export const directionParts = (counts: ConnectionCounts): number[] =>
  counts.sym === undefined ? [counts.in, counts.out] : [counts.in, counts.sym, counts.out]

/** `12 / 3 / 27`, or `12 / 27` where there is no symmetric direction. */
export const directionSplit = (counts: ConnectionCounts): string =>
  directionParts(counts).join(' / ')

export interface ConnectionColumnOptions {
  /** Whether this surface has a symmetric direction at all; drives the sub-header. */
  symmetric: boolean
  /**
   * Header caveat, e.g. that a sort covers the loaded page only. Passed by the caller because
   * only it knows whether its ordering is server-resolved or re-ranked client-side.
   */
  note?: string
  /** Whether the header offers a sort. Off where the surface cannot honour one. */
  sortable?: boolean
}

/**
 * The `Connections` column: a total with an independently sortable direction breakdown.
 *
 * Returned rather than exported as a constant because the sub-columns depend on whether the
 * surface has a symmetric direction, and the note depends on how it sorts.
 */
export const connectionColumn = (options: ConnectionColumnOptions): DataTableColumn => ({
  key: 'total',
  label: 'Connections',
  sortable: options.sortable ?? true,
  minWidth: options.symmetric ? '170px' : '150px',
  note: options.note,
  subColumns: options.symmetric
    ? [{ key: 'in', label: 'in' }, { key: 'sym', label: 'sym' }, { key: 'out', label: 'out' }]
    : [{ key: 'in', label: 'in' }, { key: 'out', label: 'out' }],
})
