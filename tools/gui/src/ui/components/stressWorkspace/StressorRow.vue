<script setup lang="ts">
/**
 * One stressor in the spreadsheet form (evaluated and kept): the first press selects the row, and the
 * canvas marks what it hits; a press on a cell of the selected row edits that cell, as `F2` edits its
 * text. `Enter` keeps, `Esc` cancels. The End state cell is a control and opens on the first press.
 * `M` opens it from the keyboard; `Delete` removes the row.
 */
import { nextTick, ref } from 'vue'
import type { DocumentTableRow } from '../../../domain/schemas/candidates'
import { cell } from '../../../domain/stressAnalysis/analysisRows'
import EndStateChooser from './EndStateChooser.vue'

type Column = 'stressor' | 'consequence' | 'kind'

const props = defineProps<{
  row: DocumentTableRow
  selected: boolean
  kinds: readonly string[]
  hits: number
  missing: readonly string[]
  endStates: readonly DocumentTableRow[]
}>()
const emit = defineEmits<{
  select: []
  change: [cells: Record<string, string>]
  remove: []
  endState: [rowId: string]
  createEndState: [name: string]
}>()

const editing = ref<Column | null>(null)
const draft = ref('')
const chooser = ref<InstanceType<typeof EndStateChooser> | null>(null)
const field = ref<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null>(null)

const begin = async (column: Column) => {
  editing.value = column
  draft.value = cell(props.row, column)
  await nextTick()
  field.value?.focus()
}
/** A press on a cell: edits it on the selected row, selects the row otherwise. */
const edit = (column: Column) => (props.selected ? begin(column) : emit('select'))
const keep = () => {
  const column = editing.value
  editing.value = null
  if (column && draft.value !== cell(props.row, column)) emit('change', { [column]: draft.value.trim() })
}
const cancel = () => { editing.value = null }

const onFieldKey = (event: KeyboardEvent) => {
  if (event.key === 'Escape') cancel()
  else if (event.key === 'Enter' && !event.shiftKey) keep()
  else return
  event.preventDefault()
  event.stopPropagation()
}
const onRowKey = (event: KeyboardEvent) => {
  if (editing.value || event.target !== event.currentTarget) return
  const actions: Readonly<Record<string, () => void>> = {
    F2: () => { void begin('stressor') },
    m: () => { void chooser.value?.show() },
    M: () => { void chooser.value?.show() },
    Delete: () => emit('remove'),
    Enter: () => emit('select'),
  }
  const action = actions[event.key]
  if (!action) return
  event.preventDefault()
  action()
}
</script>

<template>
  <tr
    class="st-row"
    :class="{ sel: selected }"
    tabindex="0"
    :data-row="row.row_id"
    @click="emit('select')"
    @keydown="onRowKey"
  >
    <td class="rid">
      {{ row.row_id }}
    </td>
    <td>
      <input
        v-if="editing === 'stressor'"
        ref="field"
        v-model="draft"
        class="cell-in"
        aria-label="Stressor"
        @keydown="onFieldKey"
        @blur="keep"
        @click.stop
      >
      <span
        v-else
        class="ed"
        @click.stop="edit('stressor')"
      >{{ cell(row, 'stressor') || '—' }}</span>
      <textarea
        v-if="editing === 'consequence'"
        ref="field"
        v-model="draft"
        class="cell-in"
        aria-label="What happens"
        @keydown="onFieldKey"
        @blur="keep"
        @click.stop
      />
      <span
        v-else
        class="ed happens"
        :class="{ unset: !cell(row, 'consequence') }"
        @click.stop="edit('consequence')"
      >{{ cell(row, 'consequence') || 'what happens…' }}</span>
      <span
        v-if="!hits"
        class="warnline"
      >⚠ No component is ticked.</span>
      <span
        v-if="!cell(row, 'consequence')"
        class="warnline"
      >⚠ What happens is not written.</span>
      <span
        v-if="missing.length"
        class="warnline"
      >⚠ Hits what the naive architecture no longer has: {{ missing.join(', ') }}</span>
    </td>
    <td>
      <select
        v-if="editing === 'kind'"
        ref="field"
        v-model="draft"
        aria-label="Kind"
        @change="keep"
        @keydown="onFieldKey"
        @blur="cancel"
        @click.stop
      >
        <option value="" />
        <option
          v-for="kind in kinds"
          :key="kind"
        >
          {{ kind }}
        </option>
      </select>
      <span
        v-else
        class="ed"
        @click.stop="edit('kind')"
      >{{ cell(row, 'kind') || '—' }}</span>
    </td>
    <td class="num">
      {{ hits || '—' }}
    </td>
    <td @click.stop>
      <EndStateChooser
        ref="chooser"
        :end-states="endStates"
        :current="cell(row, 'end_state')"
        @choose="emit('endState', $event)"
        @create="emit('createEndState', $event)"
      />
    </td>
    <td>
      <button
        type="button"
        class="rm-row"
        :aria-label="`Remove ${row.row_id}`"
        title="Remove (Delete)"
        @click.stop="emit('remove')"
      >
        ×
      </button>
    </td>
  </tr>
</template>

<style scoped>
.st-row { cursor: pointer; }
.st-row td { padding: 6px 8px; border-top: 1px solid var(--border); vertical-align: top; font-size: 12.5px; }
.st-row.sel td { background: var(--accent-soft); }
.st-row.sel { outline: 2px solid var(--accent); outline-offset: -2px; }
.rid { font-family: ui-monospace, monospace; color: var(--text-2); }
.num { text-align: center; }
.happens { display: block; color: var(--text-2); font-size: 12px; }
.happens.unset { color: var(--faint); font-style: italic; }
.sel .ed { cursor: text; }
.sel .ed:hover { box-shadow: inset 0 0 0 1px var(--border-strong); border-radius: 3px; }
.cell-in { width: 100%; font: inherit; padding: 3px 5px; }
textarea.cell-in { resize: vertical; min-height: 44px; }
.warnline { display: block; font-size: 11.5px; color: var(--warn-text); }
.rm-row { border: none; background: none; color: var(--muted); cursor: pointer; font-size: 15px; padding: 0 4px; }
.rm-row:hover, .rm-row:focus-visible { color: var(--danger-strong); }
</style>
