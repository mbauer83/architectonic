<script setup lang="ts">
/**
 * A list of rows shown as collapsible groups.
 *
 * The tree counterpart to a flat table, for surfaces whose rows fall into a handful of kinds:
 * a reader scanning for "what hazards are there" wants the hazards gathered, not interleaved
 * with everything else in last-modified order.
 *
 * Vocabulary-free by contract, exactly like `DataTable` and `FilterBar`: the caller says how to
 * group a row and how to label it, and this knows only that rows have a key, a group, and a
 * label. It names no ontology, no module and no record type — the grouping is the caller's,
 * because the caller is the only party that knows what its rows mean.
 */
import { computed, ref } from 'vue'

const props = defineProps<{
  rows: readonly Record<string, unknown>[]
  /** Property naming each row's stable identity. */
  rowKey: string
  /** The group a row belongs to; rows returning the same string are gathered together. */
  groupOf: (row: Record<string, unknown>) => string
  /** The row's display label. */
  labelOf: (row: Record<string, unknown>) => string
  /** Trailing note per row, e.g. a degree or a status. Optional. */
  noteOf?: (row: Record<string, unknown>) => string
  /** Highlighted row, if any. */
  selectedKey?: string | null
  emptyMessage?: string
}>()

const emit = defineEmits<{ rowClick: [key: string] }>()

interface Group {
  name: string
  rows: readonly Record<string, unknown>[]
}

const groups = computed<Group[]>(() => {
  const byName = new Map<string, Record<string, unknown>[]>()
  for (const row of props.rows) {
    const name = props.groupOf(row)
    const bucket = byName.get(name)
    if (bucket) bucket.push(row)
    else byName.set(name, [row])
  }
  // Alphabetical: the grouping key carries no inherent order here, and a stable one beats an
  // arbitrary one that shifts as rows arrive.
  return [...byName.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, rows]) => ({ name, rows }))
})

//: Collapsed groups. Absent means expanded, so a newly appearing group is open by default —
//: a group the reader has never seen should not arrive already hidden.
const collapsed = ref(new Set<string>())

const toggle = (name: string): void => {
  const next = new Set(collapsed.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  collapsed.value = next
}

/** A row's identity. Non-string values are not stringified into `[object Object]` — a row
 *  whose key property is missing or not a string has no usable identity, and saying so is
 *  better than emitting a key that silently collides with every other such row. */
const keyOf = (row: Record<string, unknown>): string => {
  const value = row[props.rowKey]
  return typeof value === 'string' ? value : ''
}
</script>

<template>
  <div class="row-tree">
    <p
      v-if="rows.length === 0"
      class="tree-empty"
    >
      {{ emptyMessage ?? 'Nothing to show.' }}
    </p>
    <section
      v-for="group in groups"
      :key="group.name"
      class="tree-group"
    >
      <button
        type="button"
        class="group-header"
        :aria-expanded="!collapsed.has(group.name)"
        @click="toggle(group.name)"
      >
        <span class="group-caret">{{ collapsed.has(group.name) ? '▸' : '▾' }}</span>
        <span class="group-name">{{ group.name }}</span>
        <span class="group-count">{{ group.rows.length }}</span>
      </button>
      <ul
        v-if="!collapsed.has(group.name)"
        class="group-rows"
      >
        <li
          v-for="row in group.rows"
          :key="keyOf(row)"
        >
          <button
            type="button"
            class="tree-row"
            :class="{ 'tree-row--selected': selectedKey === keyOf(row) }"
            @click="emit('rowClick', keyOf(row))"
          >
            <span class="row-label">{{ labelOf(row) }}</span>
            <span
              v-if="noteOf"
              class="row-note"
            >{{ noteOf(row) }}</span>
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.row-tree { padding: 6px 0; }
.tree-empty { font-size: 13px; color: #6b7280; padding: 12px 16px; }
.tree-group { margin-bottom: 2px; }
.group-header {
  display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 16px;
  background: none; border: none; cursor: pointer; text-align: left; font-size: 12.5px;
  font-weight: 600; color: #374151;
}
.group-header:hover { background: #f3f4f6; }
.group-caret { color: #9ca3af; width: 10px; }
.group-count {
  font-size: 11px; font-weight: 500; color: #6b7280; background: #f3f4f6;
  border-radius: 9px; padding: 1px 7px;
}
.group-rows { list-style: none; margin: 0; padding: 0; }
.tree-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%;
  padding: 4px 16px 4px 38px; background: none; border: none; cursor: pointer;
  text-align: left; font-size: 12.5px; color: #374151;
}
.tree-row:hover { background: #f3f4f6; }
/* Selected keeps its own text colour rather than inheriting the hover rule, which a
   single-class selected rule would otherwise lose to while the pointer rests on it. */
.tree-row--selected { background: #eff6ff; color: #1d4ed8; font-weight: 600; }
.tree-row--selected:hover { background: #dbeafe; color: #1d4ed8; }
.row-note { font-size: 11px; color: #6b7280; flex-shrink: 0; }
</style>
