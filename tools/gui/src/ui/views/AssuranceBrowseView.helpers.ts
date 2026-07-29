/**
 * The node-browse surface's filter and column model.
 *
 * The five filters are the same operation five times over — narrow the loaded nodes to one
 * value of one field — so they are described as data and rendered once, rather than as five
 * hand-written selects that drift apart. Which fields the *server* can order by is a separate
 * question (the store's supported sort columns), which is why only some columns are sortable.
 */

import { connectionColumn, connectionTotal } from '../components/connectionCounts'
import type { DataTableColumn } from '../components/DataTable.types'

export interface AssuranceBrowseNode extends Record<string, unknown> {
  node_id: string
  node_type: string
  name: string
  status?: string
  tlp?: string
  concern_class?: string
  binding_status?: string
  updated_at?: string
  /** The analysis that authored this node. Single-valued and fixed; participation in other
   *  analyses is a separate relation, reported on the node's own detail. */
  analysis_id?: string | null
  /** Edge counts from `/api/assurance/nodes`, over the reader's visible edge set. */
  conn_in?: number
  conn_out?: number
}

/**
 * A node's degree. No symmetric direction: assurance edges are strictly directed
 * `(source_id, target_id)` with a free-text `conn_type` and no ontology to mark a relation
 * undirected, so — unlike the architecture surface — there is no third number to report.
 */
export const nodeConnections = (node: AssuranceBrowseNode): { in: number; out: number } =>
  ({ in: node.conn_in ?? 0, out: node.conn_out ?? 0 })

export const nodeConnectionTotal = (node: AssuranceBrowseNode): number =>
  connectionTotal(nodeConnections(node))

export type FilterField = 'node_type' | 'status' | 'concern_class' | 'tlp' | 'binding_status'

export interface NodeFilter {
  field: FilterField
  /** The unfiltered choice, e.g. "All types" — also the accessible name of the control. */
  allLabel: string
}

export const NODE_FILTERS: readonly NodeFilter[] = [
  { field: 'node_type', allLabel: 'All types' },
  { field: 'status', allLabel: 'All statuses' },
  { field: 'concern_class', allLabel: 'All concerns' },
  { field: 'tlp', allLabel: 'All TLP' },
  { field: 'binding_status', allLabel: 'All binding' },
]

export type FilterSelection = Record<FilterField, string>

export const noFilters = (): FilterSelection => ({
  node_type: '',
  status: '',
  concern_class: '',
  tlp: '',
  binding_status: '',
})

/** The distinct values a filter can offer, drawn from the loaded nodes (blanks excluded — an
 * absent value is what "All" already covers). */
export const filterOptions = (
  nodes: readonly AssuranceBrowseNode[],
  field: FilterField,
): string[] => [...new Set(nodes.map((node) => node[field] ?? '').filter(Boolean))].sort()

export const matchesFilters = (node: AssuranceBrowseNode, selection: FilterSelection): boolean =>
  NODE_FILTERS.every(({ field }) => !selection[field] || node[field] === selection[field])

export const filterNodes = (
  nodes: readonly AssuranceBrowseNode[],
  selection: FilterSelection,
): AssuranceBrowseNode[] => nodes.filter((node) => matchesFilters(node, selection))

/**
 * Columns whose header offers a sort are exactly those the store can order by; the rest are
 * displayed and filtered only, never given an affordance that would silently do nothing.
 *
 * `status` and `concern_class` were filterable here long before they were visible, which meant
 * narrowing by a field the reader could not see the value of. The `Connections` column is the
 * shared one the architecture browse surface uses, minus the symmetric direction assurance has
 * no notion of; it is not sortable because the store cannot order by a degree it does not
 * store, and a header that silently did nothing is exactly what the rule above forbids.
 */
export const BROWSE_COLUMNS: readonly DataTableColumn[] = [
  { key: 'node_type', label: 'Type', sortable: true },
  { key: 'name', label: 'Name', sortable: true },
  { key: 'status', label: 'Status', sortable: true },
  { key: 'concern_class', label: 'Concern' },
  connectionColumn({ symmetric: false, sortable: false }),
  { key: 'tlp', label: 'TLP' },
  { key: 'binding_status', label: 'Binding' },
  { key: 'updated_at', label: 'Last modified', sortable: true },
]

export const DEFAULT_SORT_FIELD = 'updated_at'
export const DEFAULT_SORT_DIRECTION = 'desc'


// ── Analysis scope, as the URL carries it ─────────────────────────────────────
/**
 * The scope lives in the URL, exactly as the architecture catalog's group and domain do. A local ref
 * looked equivalent and was not: every link that names an analysis — the filing tree in the nav, a
 * provenance chip on a node — arrived, set nothing, and appeared to do nothing at all. State a link
 * can carry has to live where a link can put it.
 */

/** The `?analysis=` value meaning "the nodes with no analysis". A reserved word rather than an id:
 *  absence is not a value the store's node filter can express. */
export const NO_ANALYSIS_SCOPE = 'none'

/** The raw scope from the query, or null when unscoped. */
export const analysisScopeOf = (raw: unknown): string | null =>
  typeof raw === 'string' && raw ? raw : null

/** The scope as the *store* understands it — the reserved word is not an id to send it. */
export const storeAnalysisId = (scope: string | null): string | null =>
  scope === NO_ANALYSIS_SCOPE ? null : scope

/** Narrow to the requested scope. Only the unattributed case is filtered here; a real analysis id
 *  is applied by the store, which can do it before the exposure filter. */
export const scopeNodes = (
  nodes: readonly AssuranceBrowseNode[],
  scope: string | null,
): readonly AssuranceBrowseNode[] =>
  scope === NO_ANALYSIS_SCOPE ? nodes.filter((node) => !node.analysis_id) : nodes
