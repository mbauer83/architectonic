<script setup lang="ts">
/**
 * The Adaptations tab (06·6, Q39): every candidate stacked on the naive architecture, each saying what
 * it stacks on and which end states it answers, and below it the selected one's operations against
 * *against*. *New candidate on top…* stacks a new candidate on the selected one and records it as an
 * adaptation of the end state it answers. A row takes focus, and Enter or Space selects it.
 */
import { useCan } from '../../composables/usePermissions'
import { computed, ref } from 'vue'
import { cell, cellIds, endStateName } from '../../../domain/stressAnalysis/analysisRows'
import { chainOf, stackLine } from '../../../domain/candidates/candidateStack'
import type { Candidates } from '../../composables/useCandidates'
import type { StressAnalysis } from '../../composables/useStressAnalysis'
import CandidateOperations from '../candidates/CandidateOperations.vue'

const props = defineProps<{
  analysis: StressAnalysis; candidates: Candidates
  /** The element selected on the canvas, by stable id. */
  framed?: string | null
}>()
const emit = defineEmits<{ frame: [target: string | null]; sketch: [id: string] }>()

const adaptations = computed(() =>
  props.candidates.inStack.value.filter((one) => one.id !== props.analysis.naiveId.value))
const answers = (id: string): string => props.analysis.adaptations.value
  .filter((row) => cell(row, 'candidate_architecture') === id)
  .flatMap((row) => cellIds(row, 'end_states'))
  .map((rowId) => endStateName(props.analysis.endStates.value, rowId))
  .join(', ')
const depth = (id: string): number => chainOf(id, props.candidates.all.value).length - 2

const stacking = ref(false)
const name = ref('')
const endState = ref('')
const stackOn = computed(() => props.candidates.selected.value ?? props.analysis.naiveId.value)
const stackOnName = computed(() => props.candidates.all.value.find((one) => one.id === stackOn.value)?.name ?? '')
const create = async () => {
  const id = await props.candidates.stackOn(stackOn.value, name.value.trim())
  if (!id) return
  if (endState.value) {
    await props.analysis.edit('adaptations', [{
      op: 'add', cells: { end_states: [endState.value], candidate_architecture: id, integration: 'candidate' },
    }])
  }
  stacking.value = false
  name.value = ''
  emit('sketch', id)
}
const mayCreate = useCan('changes_create_candidate')
</script>

<template>
  <div data-testid="adaptations-tab">
    <table class="tbl cand-tree">
      <thead><tr><th>Adaptation</th><th>Answers</th><th>State</th></tr></thead>
      <tbody>
        <tr
          v-for="one in adaptations"
          :key="one.id"
          class="oprow"
          :class="{ sel: one.id === candidates.selected.value }"
          :data-candidate="one.id"
          tabindex="0"
          :aria-selected="one.id === candidates.selected.value"
          @click="candidates.select(one.id)"
          @keydown.enter.prevent="candidates.select(one.id)"
          @keydown.space.prevent="candidates.select(one.id)"
        >
          <td>
            <span
              class="ind"
              :style="{ paddingLeft: `${Math.max(depth(one.id), 0) * 14}px` }"
            >{{ depth(one.id) > 0 ? '└ ' : '' }}</span><b>{{ one.name }}</b>
            <span class="role">adaptation · {{ stackLine(one.id, candidates.all.value) }}</span>
          </td>
          <td>{{ answers(one.id) || '—' }}</td>
          <td><span class="state">{{ one.state }}</span></td>
        </tr>
      </tbody>
    </table>
    <p
      v-if="!adaptations.length"
      class="empty"
    >
      No adaptation yet. An adaptation is a candidate architecture stacked on the naive architecture
      that answers an end state.
    </p>
    <div class="new">
      <button
        v-if="!stacking"
        type="button"
        class="btn btn-sm"
        data-testid="new-candidate"
        :disabled="!mayCreate.allowed"
        :title="mayCreate.allowed ? undefined : mayCreate.reason"
        @click="stacking = true"
      >
        New candidate on top of {{ stackOnName }}…
      </button>
      <form
        v-else
        class="new-form"
        @submit.prevent="create"
      >
        <label>Name <input
          v-model="name"
          required
          autofocus
        ></label>
        <label>Answers <select v-model="endState">
          <option value="">no end state yet</option>
          <option
            v-for="row in analysis.endStates.value"
            :key="row.row_id"
            :value="row.row_id"
          >{{ row.row_id }} {{ cell(row, 'end_state') }}</option>
        </select></label>
        <button
          type="submit"
          class="btn btn-sm btn-primary"
        >
          Stack on {{ stackOnName }}
        </button>
        <button
          type="button"
          class="btn btn-sm"
          @click="stacking = false"
        >
          Cancel
        </button>
      </form>
    </div>
    <CandidateOperations
      v-if="candidates.selected.value && candidates.selected.value !== analysis.naiveId.value"
      :candidates="candidates"
      role="adaptation"
      :name-of="analysis.nameOf"
      :framed="framed"
      @frame="emit('frame', $event)"
      @sketch="emit('sketch', $event)"
    />
  </div>
</template>

<style scoped>
.tbl { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.tbl th { text-align: left; font-size: 11px; text-transform: uppercase; color: var(--muted); padding: 4px 8px; }
.tbl td { padding: 6px 8px; border-top: 1px solid var(--border); vertical-align: top; }
.oprow { cursor: pointer; }
.oprow.sel td { background: var(--accent-soft); }
.oprow:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.ind { color: var(--faint); font-family: ui-monospace, monospace; }
.role { display: block; font-size: 11px; color: var(--muted); }
.state { font-size: 11px; font-weight: 600; color: var(--text-2); }
.empty { padding: 10px; font-size: 12.5px; color: var(--muted); }
.new { padding: 8px 10px; border-top: 1px solid var(--border); }
.new-form { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; font-size: 12px; }
.new-form input, .new-form select { font: inherit; margin-left: 4px; }
</style>
