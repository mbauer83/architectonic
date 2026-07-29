// @vitest-environment jsdom
//
// The shared browse table, driven through a real mount: what a host relies on is the rendered
// structure (columns, sub-columns, slot content, selection styling) and the events, so both are
// asserted against the DOM rather than against extracted helpers.
import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, type App } from 'vue'
import DataTable from '../DataTable.vue'
import type { DataTableColumn } from '../DataTable.types'

interface Row extends Record<string, unknown> {
  id: string
  name: string
  total: number
  last_updated: string | null
}

const ROWS: Row[] = [
  { id: 'a', name: 'Alpha', total: 3, last_updated: '2026-01-01T00:00:00Z' },
  { id: 'b', name: 'Bravo', total: 7, last_updated: null },
]

const COLUMNS: readonly DataTableColumn[] = [
  { key: 'name', label: 'Name', sortable: true },
  {
    key: 'total',
    label: 'Connections',
    sortable: true,
    note: 'this page only',
    subColumns: [
      { key: 'in', label: 'in' },
      { key: 'sym', label: 'sym' },
      { key: 'out', label: 'out' },
    ],
  },
  { key: 'last_updated', label: 'Last modified', sortable: true },
  { key: 'status', label: 'Status' },
]

let mounted: App | null = null

const render = (props: Record<string, unknown>, slots: Record<string, unknown> = {}) => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({
    render: () => h(DataTable, { columns: COLUMNS, rows: ROWS, rowKey: 'id', ...props }, slots),
  })
  app.mount(host)
  mounted = app
  return host
}

afterEach(() => {
  mounted?.unmount()
  mounted = null
  document.body.innerHTML = ''
})

const headerButtons = (host: HTMLElement) =>
  [...host.querySelectorAll('thead button')].map((b) => (b.textContent ?? '').trim())

describe('DataTable rendering', () => {
  it('renders one header per column and one row per record', () => {
    const host = render({})
    expect([...host.querySelectorAll('thead th')].map((th) => (th.textContent ?? '').trim().split(' ')[0]))
      .toEqual(['Name', 'Connections', 'Last', 'Status'])
    expect(host.querySelectorAll('tbody tr')).toHaveLength(2)
  })

  it('renders a cell value with no slot, and slot content when given', () => {
    const plain = render({})
    expect((plain.querySelector('tbody tr td') as HTMLElement).textContent).toBe('Alpha')

    mounted?.unmount()
    document.body.innerHTML = ''

    const slotted = render({}, {
      name: ({ row }: { row: Row }) => h('a', { class: 'entity-link' }, row.name.toUpperCase()),
    })
    expect((slotted.querySelector('td .entity-link') as HTMLElement).textContent).toBe('ALPHA')
  })

  it('renders a sub-column group as an independently sortable second header line', () => {
    const host = render({})
    expect(headerButtons(host)).toEqual([
      'Name', 'Connections', 'in', 'sym', 'out', 'Last modified',
    ])
    expect((host.querySelector('.data-table__note') as HTMLElement).textContent).toContain('this page only')
  })

  it('shows the empty slot instead of rows when there are none', () => {
    const host = render({ rows: [], emptyMessage: 'No entities found.' })
    expect(host.querySelectorAll('.data-table__row')).toHaveLength(0)
    expect((host.querySelector('.data-table__empty') as HTMLElement).textContent).toContain('No entities found.')
  })
})

describe('DataTable sorting', () => {
  const clickHeader = (host: HTMLElement, label: string) => {
    const button = [...host.querySelectorAll('thead button')]
      .find((b) => (b.textContent ?? '').trim().startsWith(label))
    ;(button as HTMLButtonElement).click()
  }

  it('cycles ascending, descending, then back to no sort', () => {
    const sorts: Array<{ key: string | null; direction: string }> = []
    const host = render({
      sortKey: null,
      sortDir: 'asc',
      onSort: (payload: { key: string | null; direction: string }) => sorts.push(payload),
    })

    clickHeader(host, 'Name')
    expect(sorts.at(-1)).toEqual({ key: 'name', direction: 'asc' })

    mounted?.unmount()
    document.body.innerHTML = ''
    const ascending = render({
      sortKey: 'name',
      sortDir: 'asc',
      onSort: (payload: { key: string | null; direction: string }) => sorts.push(payload),
    })
    clickHeader(ascending, 'Name')
    expect(sorts.at(-1)).toEqual({ key: 'name', direction: 'desc' })

    mounted?.unmount()
    document.body.innerHTML = ''
    const descending = render({
      sortKey: 'name',
      sortDir: 'desc',
      onSort: (payload: { key: string | null; direction: string }) => sorts.push(payload),
    })
    clickHeader(descending, 'Name')
    expect(sorts.at(-1)).toEqual({ key: null, direction: 'asc' })
  })

  it('reports the state through v-model updates too', () => {
    const keys: Array<string | null> = []
    const directions: string[] = []
    const host = render({
      'onUpdate:sortKey': (key: string | null) => keys.push(key),
      'onUpdate:sortDir': (direction: string) => directions.push(direction),
    })
    clickHeader(host, 'Last modified')
    expect(keys).toEqual(['last_updated'])
    expect(directions).toEqual(['asc'])
  })

  it('sorts a sub-column independently of its parent column', () => {
    const sorts: Array<{ key: string | null }> = []
    const host = render({ onSort: (payload: { key: string | null }) => sorts.push(payload) })
    clickHeader(host, 'sym')
    expect(sorts.at(-1)?.key).toBe('sym')
  })

  it('marks the sorted column for assistive technology and shows a direction arrow', () => {
    const host = render({ sortKey: 'last_updated', sortDir: 'desc' })
    const headers = [...host.querySelectorAll('thead th')]
    const sorted = headers.find((th) => th.getAttribute('aria-sort') === 'descending')
    expect((sorted?.textContent ?? '')).toContain('↓')
    expect(headers.filter((th) => th.getAttribute('aria-sort') === 'none')).toHaveLength(2)
  })

  it('marks a column sorted by one of its sub-columns, not just by its own key', () => {
    const host = render({ sortKey: 'out', sortDir: 'asc' })
    const connections = [...host.querySelectorAll('thead th')]
      .find((th) => (th.textContent ?? '').includes('Connections'))
    expect(connections?.getAttribute('aria-sort')).toBe('ascending')
  })
})

describe('DataTable rows', () => {
  it('emits the row key on click only when the surface is selectable', () => {
    const clicks: string[] = []
    const inert = render({ onRowClick: (key: string) => clicks.push(key) })
    ;(inert.querySelector('tbody tr') as HTMLElement).click()
    expect(clicks).toEqual([])

    mounted?.unmount()
    document.body.innerHTML = ''

    const selectable = render({ selectable: true, onRowClick: (key: string) => clicks.push(key) })
    ;(selectable.querySelectorAll('tbody tr')[1] as HTMLElement).click()
    expect(clicks).toEqual(['b'])
  })

  it('styles the selected row and only that row', () => {
    const host = render({ selectable: true, selectedKey: 'b' })
    const rows = [...host.querySelectorAll('tbody tr')]
    expect(rows[0].className).not.toContain('data-table__row--selected')
    expect(rows[1].className).toContain('data-table__row--selected')
  })

  it('applies a host-supplied row class', () => {
    const host = render({ rowClass: (row: Row) => (row.id === 'a' ? 'row--global' : undefined) })
    const rows = [...host.querySelectorAll('tbody tr')]
    expect(rows[0].className).toContain('row--global')
    expect(rows[1].className).not.toContain('row--global')
  })
})
