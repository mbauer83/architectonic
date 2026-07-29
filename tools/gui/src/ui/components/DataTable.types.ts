/**
 * The column and sort vocabulary of the shared browse table (`DataTable.vue`).
 *
 * Kept in a plain module rather than exported from the component: a host view, a helper module,
 * and a test all describe columns, and a type that lives inside a single-file component is only
 * resolvable to consumers that can compile that component.
 */

export interface DataTableSubColumn {
  /** Sort key this sub-column reports. */
  key: string
  label: string
}

export interface DataTableColumn {
  /** Cell slot name, and the sort key when `sortable`. */
  key: string
  label: string
  sortable?: boolean
  align?: 'left' | 'right'
  /** A second header line of independently sortable keys, for a broken-down cell. */
  subColumns?: readonly DataTableSubColumn[]
  /** Header caveat shown under the label — e.g. that the order covers this page only. */
  note?: string
  /** Optional CSS min-width hint for narrow or fixed columns. */
  minWidth?: string
}

export type SortDirection = 'asc' | 'desc'

/** What a header click resolves to; a null key means "back to the natural order". */
export interface SortRequest {
  key: string | null
  direction: SortDirection
}
