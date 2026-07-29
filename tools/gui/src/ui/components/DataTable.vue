<script setup lang="ts" generic="Row extends Record<string, unknown>">
/**
 * The one sortable table both browse surfaces render.
 *
 * It owns the parts that were being re-invented per surface — header/sort affordances, the
 * three-state sort cycle, selection and row styling — and nothing about what a cell means: a
 * column names a slot, and the host fills it. A column may also carry sub-columns, each
 * independently sortable, for a cell that shows a total broken down into parts (the entity
 * catalog's connection counts).
 *
 * Sorting is reported, never performed: whether an order is resolved on the server over the
 * whole population or in the client over the current page is the host's decision, and the
 * distinction matters enough on a paginated list that a column can carry a `note` saying so.
 */
import { computed } from 'vue'
import type { DataTableColumn, SortDirection, SortRequest } from './DataTable.types'

const props = withDefaults(
  defineProps<{
    columns: readonly DataTableColumn[]
    rows: readonly Row[]
    /** Row field holding the stable identity used for keys, selection, and events. */
    rowKey: string
    sortKey?: string | null
    sortDir?: SortDirection
    /** Identity of the currently selected row, for a selection-driven surface. */
    selectedKey?: string | null
    /** Marks rows as clickable; a surface whose rows only contain links leaves this off. */
    selectable?: boolean
    /** Extra class per row — tier shading, status emphasis, whatever the host distinguishes. */
    rowClass?: (row: Row) => string | undefined
    emptyMessage?: string
  }>(),
  {
    sortKey: null,
    sortDir: 'asc',
    selectedKey: null,
    selectable: false,
    rowClass: undefined,
    emptyMessage: 'Nothing to show.',
  },
)

const emit = defineEmits<{
  'update:sortKey': [key: string | null]
  'update:sortDir': [direction: SortDirection]
  /** The resolved order after a header click — null key means "back to natural order". */
  sort: [payload: SortRequest]
  'row-click': [key: string, row: Row]
}>()

/** Row identity, read from the caller-named field. Only a primitive can be an identity; a
 * structured value would stringify to `[object Object]` and collide across every row. */
const asText = (value: unknown): string => {
  if (typeof value === 'string') return value
  return typeof value === 'number' || typeof value === 'boolean' ? String(value) : ''
}

const keyOf = (row: Row): string => asText(row[props.rowKey])

/** asc → desc → unsorted, so a third click undoes the sort instead of trapping the reader. */
const cycle = (key: string) => {
  const next: SortRequest =
    props.sortKey !== key
      ? { key, direction: 'asc' }
      : props.sortDir === 'asc'
        ? { key, direction: 'desc' }
        : { key: null, direction: 'asc' }
  emit('update:sortKey', next.key)
  emit('update:sortDir', next.direction)
  emit('sort', next)
}

const arrow = (key: string): string => {
  if (props.sortKey !== key) return ''
  return props.sortDir === 'asc' ? '↑' : '↓'
}

/** A column counts as sorted when the active key is its own or one of its sub-columns' — a
 * reader using assistive technology otherwise gets no signal that the Connections column is
 * ordered by its `out` breakdown. */
const ariaSort = (column: DataTableColumn): 'ascending' | 'descending' | 'none' | undefined => {
  if (!column.sortable && !column.subColumns) return undefined
  const owned = [column.key, ...(column.subColumns ?? []).map((sub) => sub.key)]
  if (props.sortKey === null || !owned.includes(props.sortKey)) return 'none'
  return props.sortDir === 'asc' ? 'ascending' : 'descending'
}

const hasRows = computed(() => props.rows.length > 0)
</script>

<template>
  <table class="data-table">
    <thead>
      <tr>
        <th
          v-for="column in columns"
          :key="column.key"
          :class="[`data-table__th--${column.align ?? 'left'}`]"
          :style="column.minWidth ? { minWidth: column.minWidth } : undefined"
          :aria-sort="ariaSort(column)"
        >
          <button
            v-if="column.sortable"
            type="button"
            class="data-table__sort"
            @click="cycle(column.key)"
          >
            {{ column.label }} {{ arrow(column.key) }}
          </button>
          <span v-else>{{ column.label }}</span>

          <span
            v-if="column.subColumns"
            class="data-table__subheader"
          >(<template
            v-for="(sub, index) in column.subColumns"
            :key="sub.key"
          ><span v-if="index > 0"> / </span><button
            type="button"
            class="data-table__sort data-table__sort--sub"
            @click="cycle(sub.key)"
          >{{ sub.label }} {{ arrow(sub.key) }}</button></template>)</span>

          <span
            v-if="column.note"
            class="data-table__note"
          >{{ column.note }}</span>
        </th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="row in rows"
        :key="keyOf(row)"
        class="data-table__row"
        :class="[
          rowClass?.(row),
          {
            'data-table__row--clickable': selectable,
            'data-table__row--selected': selectedKey !== null && keyOf(row) === selectedKey,
          },
        ]"
        @click="selectable && emit('row-click', keyOf(row), row)"
      >
        <td
          v-for="column in columns"
          :key="column.key"
          :class="[`data-table__td--${column.align ?? 'left'}`]"
        >
          <slot
            :name="column.key"
            :row="row"
            :value="row[column.key]"
          >
            {{ asText(row[column.key]) }}
          </slot>
        </td>
      </tr>
      <tr v-if="!hasRows">
        <td
          :colspan="columns.length"
          class="data-table__empty"
        >
          <slot name="empty">
            {{ emptyMessage }}
          </slot>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.data-table {
  width: 100%;
  border-collapse: collapse;
  background: white;
}
.data-table th,
.data-table td { padding: 10px 14px; text-align: left; }
.data-table th {
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: #6b7280;
  white-space: nowrap;
}
.data-table td { border-bottom: 1px solid #f3f4f6; font-size: 13px; }
.data-table tr:last-child td { border-bottom: 0; }
.data-table__row:hover td { background: #f9fafb; }
.data-table__th--right, .data-table__td--right { text-align: right; }

.data-table__sort {
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
}
.data-table__sort:hover { color: #374151; }
.data-table__subheader {
  display: block;
  margin-top: 2px;
  font-size: 9px;
  font-weight: 400;
  letter-spacing: 0;
  text-transform: none;
  color: #9ca3af;
}
.data-table__note {
  display: block;
  margin-top: 2px;
  font-size: 9px;
  font-weight: 400;
  letter-spacing: 0;
  text-transform: none;
  color: #9ca3af;
}
.data-table__row--clickable { cursor: pointer; }
.data-table__row--clickable:hover td { background: #f0f9ff; }
.data-table__row--selected td { background: #eff6ff; }
.data-table__row--selected td:first-child { box-shadow: inset 3px 0 0 #2563eb; }
.data-table__empty { color: #9ca3af; font-size: 13px; }
</style>
