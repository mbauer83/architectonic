<script setup lang="ts">
/**
 * The Stressors tab (06·2, 06·3): counts by kind, coverage hints, the stressors as an editable table
 * with an End state column, the coupling per pair of components (Q30), and the incidence grid for
 * the stressor in focus.
 */
import { computed, ref } from 'vue'
import { endStateName } from '../../../domain/stressAnalysis/analysisRows'
import { coverageHints } from '../../../domain/stressAnalysis/analysisProgress'
import type { AnalysisEdits } from '../../composables/useAnalysisEdits'
import type { StressAnalysis } from '../../composables/useStressAnalysis'
import CoverageHintsPanel from './CoverageHintsPanel.vue'
import IncidenceGrid from './IncidenceGrid.vue'
import StressorRow from './StressorRow.vue'

const props = defineProps<{ analysis: StressAnalysis; edits: AnalysisEdits; selected: string | null }>()
const emit = defineEmits<{
  select: [rowId: string | null]
  show: [stableOrFullId: string]
  openRow: [tab: 'stressors' | 'end-states', rowId: string]
}>()

const showHints = ref(false)
/** The row just added, whose text field opens for typing. */
const fresh = ref<string | null>(null)

const byKind = computed(() => Object.entries(props.analysis.progress.value?.coverage.by_kind ?? {}))
const kinds = computed(() => [...new Set([
  ...byKind.value.map(([kind]) => kind), ...(props.analysis.progress.value?.coverage.unused_kinds ?? []),
])].sort())
const hints = computed(() => {
  const progress = props.analysis.progress.value
  return progress ? coverageHints(progress, props.analysis.nameOf) : null
})
const focused = computed(() => props.analysis.stressors.value.find((row) => row.row_id === props.selected) ?? null)
const coupling = computed(() => [...props.analysis.incidence.value?.coupling ?? []].sort((a, b) => b.count - a.count))

/** Add a row, select it, and put its text field in focus (*Add stressor*, or a coverage hint). */
const add = async (cells: Readonly<Record<string, string>> = {}) => {
  const id = await props.edits.addStressor(cells)
  if (!id) return
  emit('select', id)
  fresh.value = id
}
const aboutElement = async (id: string) => {
  const added = await props.edits.addStressor({ subject: id })
  if (added) await props.edits.tick(added, id)
  if (added) emit('select', added)
}
</script>

<template>
  <div data-testid="stressors-tab">
    <div class="kinds">
      <b>By kind</b>
      <span
        v-for="[kind, count] in byKind"
        :key="kind"
        class="k"
      >{{ kind }} {{ count }}</span>
      <span
        v-for="kind in analysis.progress.value?.coverage.unused_kinds ?? []"
        :key="kind"
        class="k low"
      >{{ kind }} 0</span>
      <span class="sp" />
      <button
        type="button"
        class="btn btn-sm"
        :aria-pressed="showHints"
        @click="showHints = !showHints"
      >
        Coverage hints
      </button>
      <button
        type="button"
        class="btn btn-sm"
        data-testid="add-stressor"
        :disabled="analysis.saving.value"
        @click="add()"
      >
        Add stressor
      </button>
    </div>
    <CoverageHintsPanel
      v-if="showHints && hints"
      :hints="hints"
      :end-state-name="(rowId: string) => endStateName(analysis.endStates.value, rowId)"
      @close="showHints = false"
      @show="emit('show', $event)"
      @about-element="aboutElement"
      @of-kind="add({ kind: $event })"
      @open-row="(tab, row) => emit('openRow', tab, row)"
    />
    <p class="help">
      To group a stressor under an end state: its <b>End state</b> cell, or focus it and press <kbd>M</kbd>,
      or drag it between cards in <i>End states</i>.
    </p>
    <div class="scroll">
      <table class="tbl">
        <thead>
          <tr><th>Id</th><th>Stressor · what happens</th><th>Kind</th><th>Hits</th><th>End state</th><th /></tr>
        </thead>
        <tbody>
          <StressorRow
            v-for="row in analysis.stressors.value"
            :key="row.row_id"
            :row="row"
            :fresh="row.row_id === fresh"
            :selected="row.row_id === selected"
            :kinds="kinds"
            :hits="analysis.hitsOf(row.row_id).length"
            :missing="analysis.missingOf(row.row_id).map(analysis.nameOf)"
            :end-states="analysis.endStates.value"
            @opened="fresh = null"
            @select="emit('select', row.row_id === selected ? null : row.row_id)"
            @change="edits.changeStressor(row, $event)"
            @remove="edits.removeStressor(row)"
            @end-state="edits.setEndState(row, $event)"
            @create-end-state="edits.createEndStateFor(row, $event)"
          />
        </tbody>
      </table>
      <p
        v-if="!analysis.stressors.value.length"
        class="empty"
      >
        No stressors yet. <i>Add stressor</i>, or open the coverage hints.
      </p>
    </div>
    <details class="coupling">
      <summary>
        <b>Coupling</b>
        <span class="cnt">
          {{ coupling.length }} pair{{ coupling.length === 1 ? '' : 's' }} hit together by stressors
        </span>
      </summary>
      <ul>
        <li
          v-for="pair in coupling"
          :key="`${pair.left}|${pair.right}`"
        >
          {{ analysis.nameOf(pair.left) }} and {{ analysis.nameOf(pair.right) }}: hit together by
          {{ pair.count }} stressor{{ pair.count === 1 ? '' : 's' }}
        </li>
      </ul>
    </details>
    <IncidenceGrid
      v-if="focused"
      :title="`Incidence — ${focused.row_id} in focus`"
      :stressors="[focused]"
      :ticks="analysis.ticks.value"
      :name-of="analysis.nameOf"
      @untick="edits.untick"
      @tick="edits.tick"
      @note="edits.note"
    />
  </div>
</template>

<style scoped>
.kinds {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 10px;
  font-size: 12px;
  align-items: center;
  border-bottom: 1px solid var(--border);
}
.k { padding: 1px 7px; border-radius: 3px; background: var(--soft); color: var(--text-2); }
.k.low { background: var(--warn-soft); color: var(--warn-text); }
.sp { flex: 1; }
.help { padding: 6px 10px; font-size: 12px; color: var(--text-2); margin: 0; }
.help kbd {
  font: 10px ui-monospace, monospace;
  border: 1px solid var(--border-strong);
  border-radius: 3px;
  padding: 0 3px;
}
.scroll { max-height: calc(100vh - 440px); min-height: 160px; overflow: auto; }
.tbl { width: 100%; border-collapse: collapse; }
.tbl th {
  text-align: left;
  font-size: 11px;
  text-transform: uppercase;
  color: var(--muted);
  padding: 4px 8px;
  position: sticky;
  top: 0;
  background: var(--surface);
}
.empty { padding: 10px; font-size: 12.5px; color: var(--muted); }
.coupling { margin: 6px 10px; font-size: 12.5px; }
.coupling summary { cursor: pointer; padding: 4px 0; }
.coupling .cnt { color: var(--muted); }
.coupling ul { margin: 4px 0 4px 18px; }
</style>
