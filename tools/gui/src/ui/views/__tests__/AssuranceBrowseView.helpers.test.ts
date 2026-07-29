import { describe, expect, it } from 'vitest'
import {
  BROWSE_COLUMNS,
  DEFAULT_SORT_DIRECTION,
  DEFAULT_SORT_FIELD,
  NODE_FILTERS,
  filterNodes,
  filterOptions,
  matchesFilters,
  noFilters,
  nodeConnectionTotal,
  type AssuranceBrowseNode,
} from '../AssuranceBrowseView.helpers'

const NODES: AssuranceBrowseNode[] = [
  {
    node_id: 'LSS@1', node_type: 'loss', name: 'Alpha Loss', status: 'draft',
    tlp: 'TLP:WHITE', concern_class: 'safety', binding_status: 'bound',
    updated_at: '2026-07-20T00:00:00Z',
  },
  {
    node_id: 'HAZ@2', node_type: 'hazard', name: 'Bravo Hazard', status: 'active',
    tlp: 'TLP:AMBER', concern_class: 'security', binding_status: 'unbound',
    updated_at: '2026-07-22T00:00:00Z',
  },
  { node_id: 'CON@3', node_type: 'constraint', name: 'Charlie Constraint', status: 'draft' },
]

describe('filterOptions', () => {
  it('offers each distinct value once, sorted', () => {
    expect(filterOptions(NODES, 'node_type')).toEqual(['constraint', 'hazard', 'loss'])
    expect(filterOptions(NODES, 'status')).toEqual(['active', 'draft'])
  })

  it('omits blanks — "All" already covers a node with no value', () => {
    expect(filterOptions(NODES, 'binding_status')).toEqual(['bound', 'unbound'])
    expect(filterOptions([], 'tlp')).toEqual([])
  })
})

describe('matchesFilters', () => {
  it('accepts everything when nothing is selected', () => {
    expect(NODES.every((node) => matchesFilters(node, noFilters()))).toBe(true)
  })

  it('requires every selected filter to match, not any of them', () => {
    const selection = { ...noFilters(), node_type: 'hazard', status: 'active' }
    expect(matchesFilters(NODES[1], selection)).toBe(true)

    const conflicting = { ...noFilters(), node_type: 'hazard', status: 'draft' }
    expect(matchesFilters(NODES[1], conflicting)).toBe(false)
  })

  it('excludes a node that has no value for a selected field', () => {
    expect(matchesFilters(NODES[2], { ...noFilters(), tlp: 'TLP:WHITE' })).toBe(false)
  })
})

describe('filterNodes', () => {
  it('narrows the list and preserves the server-resolved order', () => {
    const selection = { ...noFilters(), status: 'draft' }
    expect(filterNodes(NODES, selection).map((n) => n.node_id)).toEqual(['LSS@1', 'CON@3'])
  })

  it('covers all five narrowable fields', () => {
    expect(NODE_FILTERS.map((f) => f.field))
      .toEqual(['node_type', 'status', 'concern_class', 'tlp', 'binding_status'])
  })
})

describe('BROWSE_COLUMNS', () => {
  it('shows every field the reader can filter by, plus degree and last modified', () => {
    // `status` and `concern_class` were filterable long before they were visible, which meant
    // narrowing by a value the reader had no way to see.
    expect(BROWSE_COLUMNS.map((c) => c.key)).toEqual([
      'node_type', 'name', 'status', 'concern_class', 'total', 'tlp', 'binding_status',
      'updated_at',
    ])
  })

  it('offers a sort only on the fields the store can order by', () => {
    const sortable = BROWSE_COLUMNS.filter((c) => c.sortable).map((c) => c.key)
    expect(sortable).toEqual(['node_type', 'name', 'status', 'updated_at'])
  })

  it('breaks connections into in and out, with no symmetric direction', () => {
    // Assurance edges are strictly directed and carry no ontology, so there is nothing that
    // could be undirected — a permanently-zero `sym` would assert otherwise.
    const connections = BROWSE_COLUMNS.find((c) => c.key === 'total')

    expect(connections?.subColumns?.map((s) => s.key)).toEqual(['in', 'out'])
  })

  it('does not offer a sort on connections, which the store cannot order by', () => {
    expect(BROWSE_COLUMNS.find((c) => c.key === 'total')?.sortable).toBe(false)
  })

  it('defaults to most recently updated first, matching the endpoint default', () => {
    expect(DEFAULT_SORT_FIELD).toBe('updated_at')
    expect(DEFAULT_SORT_DIRECTION).toBe('desc')
  })
})

describe('nodeConnectionTotal', () => {
  it('sums the two directions the assurance model has', () => {
    expect(nodeConnectionTotal({ ...NODES[0], conn_in: 3, conn_out: 4 })).toBe(7)
  })

  it('reads a node with no counts as unconnected rather than unknown', () => {
    // The endpoint always sends both fields, including zeros; a node that predates that, or a
    // fixture that omits them, must still render a number.
    expect(nodeConnectionTotal(NODES[0])).toBe(0)
  })
})
