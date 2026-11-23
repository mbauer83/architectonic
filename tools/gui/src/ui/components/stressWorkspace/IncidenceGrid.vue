<script setup lang="ts">
/**
 * The incidence grid in focus (06·3): only ticked components. With one stressor in focus a row per
 * component it hits, with the tick's note; with an end state in focus the grid turns — components
 * down, its stressors across. A press on a tick takes it back; the canvas adds one.
 */
import { computed, ref } from 'vue'
import type { DocumentTableRow } from '../../../domain/schemas/candidates'
import type { Tick } from '../../../domain/stressAnalysis/analysisRows'
import { cell, componentsHitBy } from '../../../domain/stressAnalysis/analysisRows'

const props = defineProps<{
  title: string
  stressors: readonly DocumentTableRow[]
  ticks: readonly Tick[]
  nameOf: (id: string) => string
  /** Components down, the stressors across: how an end state in focus is read. */
  turned?: boolean
}>()
const emit = defineEmits<{
  untick: [tick: Tick]
  tick: [stressor: string, component: string]
  note: [tick: Tick, note: string]
}>()

const focused = computed(() => new Set(props.stressors.map((row) => row.row_id)))
const components = computed(() => componentsHitBy(props.ticks, focused.value))
const tickOf = (stressor: string, component: string): Tick | undefined =>
  props.ticks.find((tick) => tick.stressor === stressor && tick.component === component)
const count = (component: string): number =>
  props.stressors.filter((row) => tickOf(row.row_id, component)).length
const one = computed(() => (!props.turned && props.stressors.length === 1 ? props.stressors[0] : null))

const noting = ref<Tick | null>(null)
const draft = ref('')
const startNote = (tick: Tick) => { noting.value = tick; draft.value = tick.note }
const keepNote = () => {
  const tick = noting.value
  noting.value = null
  if (tick && draft.value.trim() !== tick.note) emit('note', tick, draft.value.trim())
}
const toggle = (stressor: string, component: string) => {
  const tick = tickOf(stressor, component)
  if (tick) emit('untick', tick)
  else emit('tick', stressor, component)
}
</script>

<template>
  <section
    class="grid"
    data-testid="incidence-grid"
  >
    <div class="grid-cap">
      <span>{{ title }}</span>
      <span class="pill">only ticked components</span>
      <span class="hint">press an element on the canvas to tick it</span>
      <slot />
    </div>
    <p
      v-if="!components.length"
      class="empty"
    >
      Nothing ticked yet. Press an element on the canvas.
    </p>
    <table
      v-else-if="one"
      class="tbl"
    >
      <thead><tr><th>Hit</th><th>Component</th><th>Note</th></tr></thead>
      <tbody>
        <tr
          v-for="component in components"
          :key="component"
        >
          <td>
            <button
              type="button"
              class="tick"
              aria-pressed="true"
              :aria-label="`Untick ${nameOf(component)}`"
              @click="toggle(one.row_id, component)"
            >
              ✓
            </button>
          </td>
          <td>{{ nameOf(component) }}</td>
          <td>
            <input
              v-if="noting && noting.component === component"
              v-model="draft"
              class="cell-in"
              aria-label="Why it is hit"
              @keydown.enter.prevent="keepNote"
              @keydown.esc.stop="noting = null"
              @blur="keepNote"
            >
            <button
              v-else
              type="button"
              class="note-btn"
              @click="startNote(tickOf(one.row_id, component)!)"
            >
              {{ tickOf(one.row_id, component)?.note || 'note…' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <table
      v-else
      class="tbl inc"
    >
      <thead>
        <tr>
          <th>Component</th>
          <th
            v-for="row in stressors"
            :key="row.row_id"
            class="col"
            :title="cell(row, 'stressor')"
          >
            {{ row.row_id }} · {{ cell(row, 'stressor') }}
          </th>
          <th>Hit by</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="component in components"
          :key="component"
        >
          <td>{{ nameOf(component) }}</td>
          <td
            v-for="row in stressors"
            :key="row.row_id"
            class="t"
          >
            <button
              type="button"
              class="tick"
              :class="{ note: tickOf(row.row_id, component)?.note }"
              :aria-pressed="!!tickOf(row.row_id, component)"
              :aria-label="`${row.row_id} hits ${nameOf(component)}`"
              @click="toggle(row.row_id, component)"
            >
              {{ tickOf(row.row_id, component) ? '✓' : '' }}
            </button>
          </td>
          <td>{{ count(component) }} of {{ stressors.length }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.grid { border-top: 1px solid var(--border); }
.grid-cap {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  padding: 8px 10px 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2);
}
.pill { background: var(--soft); border-radius: 3px; padding: 1px 6px; font-weight: 600; font-size: 11px; }
.hint { font-weight: 400; color: var(--muted); }
.empty { padding: 6px 10px 10px; font-size: 12.5px; color: var(--muted); }
.tbl { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.tbl th { text-align: left; font-size: 11px; text-transform: uppercase; color: var(--muted); padding: 4px 8px; }
.tbl td { padding: 4px 8px; border-top: 1px solid var(--border); }
.inc th.col {
  writing-mode: vertical-rl; transform: rotate(180deg); text-transform: none; font-weight: 500;
  height: 140px; max-height: 140px; overflow: hidden; vertical-align: bottom; width: 34px;
}
.t { text-align: center; width: 34px; }
.tick {
  width: 22px; height: 22px; border-radius: 4px; border: 1px solid var(--border-strong);
  background: var(--surface); cursor: pointer; font-size: 12px; line-height: 1;
}
.tick[aria-pressed="true"] { background: #1e293b; color: #fff; border-color: #1e293b; }
.tick.note::after { content: '•'; color: #f59e0b; position: relative; top: -6px; }
.note-btn {
  border: none;
  background: none;
  color: var(--text-2);
  cursor: text;
  font: inherit;
  padding: 0;
  text-align: left;
}
.cell-in { width: 100%; font: inherit; padding: 2px 4px; }
</style>
