<script setup lang="ts">
/**
 * End states as cards holding their stressors, *Ungrouped* first (06·4). A stressor moves by dragging
 * it onto a card, or by `M` and the same chooser as the End state column. Each card carries
 * **◎ Focus**, a toggle: the grid turns to that end state and the canvas marks what its stressors hit.
 */
import { computed } from 'vue'
import type { DocumentTableRow } from '../../../domain/schemas/candidates'
import type { Tick } from '../../../domain/stressAnalysis/analysisRows'
import { cell, groupedByEndState } from '../../../domain/stressAnalysis/analysisRows'
import EndStateChooser from './EndStateChooser.vue'
import IncidenceGrid from './IncidenceGrid.vue'

const props = defineProps<{
  stressors: readonly DocumentTableRow[]
  endStates: readonly DocumentTableRow[]
  ticks: readonly Tick[]
  focus: string | null
  selectedRow: string | null
  nameOf: (id: string) => string
}>()
const emit = defineEmits<{
  focus: [rowId: string | null]
  move: [stressor: DocumentTableRow, endState: string]
  createAndMove: [stressor: DocumentTableRow, name: string]
  untick: [tick: Tick]
  tick: [stressor: string, component: string]
  note: [tick: Tick, note: string]
}>()

const groups = computed(() => groupedByEndState(props.stressors, props.endStates))
const focused = computed(() => props.endStates.find((row) => row.row_id === props.focus) ?? null)
const focusedStressors = computed(() =>
  groups.value.find((group) => group.endState?.row_id === props.focus)?.stressors ?? [])

const drop = (event: DragEvent, endState: string) => {
  const id = event.dataTransfer?.getData('text/x-stressor')
  const stressor = props.stressors.find((row) => row.row_id === id)
  if (stressor && endState && cell(stressor, 'end_state') !== endState) emit('move', stressor, endState)
}
const drag = (event: DragEvent, row: DocumentTableRow) => event.dataTransfer?.setData('text/x-stressor', row.row_id)

/** Each stressor's chooser, by row id: `M` on a focused stressor opens it. */
interface Chooser { readonly show: () => Promise<void> }
const isChooser = (value: unknown): value is Chooser =>
  typeof value === 'object' && value !== null && 'show' in value && typeof value.show === 'function'
const choosers = new Map<string, Chooser>()
const keepChooser = (rowId: string, chooser: unknown) => {
  if (isChooser(chooser)) choosers.set(rowId, chooser)
  else choosers.delete(rowId)
}
</script>

<template>
  <div data-testid="end-states-tab">
    <div
      v-for="group in groups"
      :key="group.endState?.row_id ?? 'ungrouped'"
      class="es"
      :class="{ sel: group.endState && group.endState.row_id === focus }"
      :data-end-state="group.endState?.row_id ?? 'ungrouped'"
      @dragover.prevent
      @drop.prevent="drop($event, group.endState?.row_id ?? '')"
    >
      <div class="es-h">
        <b>{{ group.endState ? cell(group.endState, 'end_state') : 'Ungrouped' }}</b>
        <span class="cnt">{{ group.stressors.length }} stressor{{ group.stressors.length === 1 ? '' : 's' }}</span>
        <button
          v-if="group.endState"
          type="button"
          class="btn btn-sm focus-btn"
          :aria-pressed="group.endState.row_id === focus"
          @click="emit('focus', group.endState.row_id === focus ? null : group.endState.row_id)"
        >
          ◎ Focus
        </button>
      </div>
      <ul>
        <li
          v-for="row in group.stressors"
          :key="row.row_id"
          class="st"
          :class="{ sel: row.row_id === selectedRow }"
          tabindex="0"
          draggable="true"
          :data-row="row.row_id"
          @dragstart="drag($event, row)"
          @keydown.m.prevent="choosers.get(row.row_id)?.show()"
        >
          <span class="grip">⋮⋮</span>
          <span class="rid">{{ row.row_id }}</span>
          <span class="txt">{{ cell(row, 'stressor') }}</span>
          <EndStateChooser
            :ref="(chooser) => keepChooser(row.row_id, chooser)"
            class="m-chooser"
            :end-states="endStates"
            :current="cell(row, 'end_state')"
            @choose="emit('move', row, $event)"
            @create="emit('createAndMove', row, $event)"
          />
        </li>
      </ul>
      <div
        v-if="group.endState"
        class="es-f"
      >
        <span>
          Required behaviour:
          {{ cell(group.endState, 'required_behaviour') ? nameOf(cell(group.endState, 'required_behaviour')) : '—' }}
        </span>
        <span v-if="cell(group.endState, 'no_change_reason')">
          No change needed: {{ cell(group.endState, 'no_change_reason') }}
        </span>
      </div>
    </div>
    <IncidenceGrid
      v-if="focused"
      :title="`Incidence — “${cell(focused, 'end_state')}” in focus`"
      :stressors="focusedStressors"
      :ticks="ticks"
      :name-of="nameOf"
      turned
      @untick="emit('untick', $event)"
      @tick="(stressor, component) => emit('tick', stressor, component)"
      @note="(tick, note) => emit('note', tick, note)"
    >
      <button
        type="button"
        class="btn btn-sm"
        @click="emit('focus', null)"
      >
        Leave focus
      </button>
    </IncidenceGrid>
  </div>
</template>

<style scoped>
.es { border: 1px solid var(--border); border-radius: 8px; margin: 8px 10px; background: var(--surface); }
.es.sel { border-color: var(--accent); box-shadow: inset 3px 0 0 var(--accent); }
.es-h { display: flex; gap: 8px; align-items: center; padding: 8px 10px 4px; }
.es-h b { flex: 1; font-size: 13px; }
.cnt { color: var(--muted); font-size: 12px; }
.focus-btn[aria-pressed="true"] {
  background: var(--accent-soft);
  color: var(--accent-strong);
  border-color: var(--accent-border);
  font-weight: 600;
}
.es ul { list-style: none; padding: 0 10px 6px; margin: 0; }
.st {
  display: flex;
  gap: 6px;
  align-items: baseline;
  padding: 3px 6px;
  border-radius: 4px;
  font-size: 12.5px;
  cursor: grab;
}
.st:hover, .st.sel { background: var(--hover); }
.st:focus-visible { outline: 2px solid var(--accent); }
.st .txt { flex: 1; }
.grip { color: var(--faint); font-size: 11px; }
.rid { font-family: ui-monospace, monospace; color: var(--text-2); }
.m-chooser { visibility: hidden; }
.st:focus-within .m-chooser, .st:hover .m-chooser { visibility: visible; }
.es-f {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 6px 10px 8px;
  border-top: 1px solid var(--border);
  font-size: 12px;
  color: var(--text-2);
}
</style>
