<script setup lang="ts">
/**
 * The judge walk: the stressor walk's focus-one-at-a-time, over the test set and one architecture.
 * A row in focus is judged — survives, degrades or fails — with the reasoning beside it, while the
 * canvas shows the architecture being judged. A stressor that cannot be walked, or contradicts itself,
 * is struck as unusable with the reason, and leaves the denominator for every architecture.
 */
import { computed, ref, watch } from 'vue'
import type { DocumentTableRow } from '../../../domain/schemas/candidates'
import type { Verdict } from '../../../domain/schemas/stressEvaluation'
import { cell } from '../../../domain/stressAnalysis/analysisRows'
import { verdictRow } from '../../../domain/stressAnalysis/testSet'

const props = defineProps<{
  architecture: string
  name: string
  stressors: readonly DocumentTableRow[]
  verdicts: readonly DocumentTableRow[]
  selected: string | null
  saving: boolean
}>()
const emit = defineEmits<{
  select: [rowId: string | null]
  judge: [stressor: string, cells: { verdict?: Verdict; usable?: boolean; reasoning?: string }]
  restore: [stressor: string]
  done: []
}>()

const VERDICTS: readonly { readonly value: Verdict; readonly label: string }[] = [
  { value: 'survives', label: 'Survives' },
  { value: 'degrades', label: 'Degrades' },
  { value: 'fails', label: 'Fails' },
]

/** This architecture's verdict row's *column* for *stressor*; empty where it has none. */
const own = (stressor: string, column: 'verdict' | 'reasoning'): string => {
  const row = verdictRow(props.verdicts, stressor, props.architecture)
  return row ? cell(row, column) : ''
}
/** Why a stressor is struck, by whichever architecture's judge struck it; none while it is usable. */
const struck = (stressor: string): string | null => {
  const row = props.verdicts.find((one) => cell(one, 'stressor') === stressor && cell(one, 'usable') === 'false')
  return row ? cell(row, 'reasoning') || 'no reason given' : null
}
const verdictOf = (stressor: string): string => own(stressor, 'verdict')
const judged = computed(() => props.stressors.filter((row) => struck(row.row_id) || verdictOf(row.row_id)).length)
const focused = computed(() => props.stressors.find((row) => row.row_id === props.selected) ?? null)

const reasoning = ref('')
const striking = ref(false)
watch(focused, (row) => {
  reasoning.value = row ? own(row.row_id, 'reasoning') : ''
  striking.value = false
}, { immediate: true })

/** The reasoning kept on its own; not when focus moves to a verdict, which keeps it with the verdict. */
const leaveReasoning = (event: FocusEvent) => {
  const next = event.relatedTarget
  if (!(next instanceof HTMLElement && next.closest('.verdicts'))) keepReasoning()
}
const keepReasoning = () => {
  const row = focused.value
  if (!row || reasoning.value.trim() === own(row.row_id, 'reasoning')) return
  emit('judge', row.row_id, { reasoning: reasoning.value.trim() })
}
const give = (verdict: Verdict) => {
  const row = focused.value
  if (row) emit('judge', row.row_id, { verdict, usable: true, reasoning: reasoning.value.trim() })
}
const strike = () => {
  const row = focused.value
  if (row && reasoning.value.trim()) emit('judge', row.row_id, { usable: false, reasoning: reasoning.value.trim() })
  striking.value = false
}
const next = () => {
  const open = props.stressors.find((row) => row.row_id !== props.selected && !struck(row.row_id)
    && !verdictOf(row.row_id))
  emit('select', open?.row_id ?? null)
}
</script>

<template>
  <section
    class="judge"
    data-testid="judge-walk"
  >
    <div class="cap">
      <span>Judging <b>{{ name }}</b> · {{ judged }} of {{ stressors.length }} judged</span>
      <span class="sp" />
      <button
        type="button"
        class="btn btn-sm"
        @click="emit('done')"
      >
        Done
      </button>
    </div>
    <table class="tbl">
      <thead><tr><th>Id</th><th>Test stressor</th><th>Verdict</th></tr></thead>
      <tbody>
        <tr
          v-for="row in stressors"
          :key="row.row_id"
          class="jr"
          :class="{ sel: row.row_id === selected, off: struck(row.row_id) }"
          tabindex="0"
          :data-row="row.row_id"
          @click="emit('select', row.row_id === selected ? null : row.row_id)"
          @keydown.enter.self.prevent="emit('select', row.row_id)"
        >
          <td class="rid">
            {{ row.row_id }}
          </td>
          <td>{{ cell(row, 'stressor') }}</td>
          <td class="v">
            {{ struck(row.row_id) ? 'unusable' : verdictOf(row.row_id) || '—' }}
          </td>
        </tr>
      </tbody>
    </table>
    <div
      v-if="focused"
      class="focus"
    >
      <p class="what">
        <b>{{ focused.row_id }}</b> {{ cell(focused, 'stressor') }}
      </p>
      <p
        v-if="struck(focused.row_id)"
        class="struck"
      >
        Struck as unusable: {{ struck(focused.row_id) }}
        <button
          type="button"
          class="btn btn-sm"
          @click="emit('restore', focused.row_id)"
        >
          Restore
        </button>
      </p>
      <template v-else>
        <div
          class="verdicts"
          role="group"
          :aria-label="`What ${name} does under ${focused.row_id}`"
        >
          <button
            v-for="one in VERDICTS"
            :key="one.value"
            type="button"
            class="btn btn-sm"
            :aria-pressed="verdictOf(focused.row_id) === one.value"
            :disabled="saving"
            @click="give(one.value)"
          >
            {{ one.label }}
          </button>
        </div>
        <label class="why">Reasoning
          <input
            v-model="reasoning"
            class="cell-in"
            aria-label="Reasoning"
            placeholder="what happens, and why"
            @keydown.enter.prevent="keepReasoning"
            @blur="leaveReasoning"
          >
        </label>
        <div class="acts">
          <button
            v-if="!striking"
            type="button"
            class="link"
            @click="striking = true"
          >
            Strike as unusable…
          </button>
          <span
            v-else
            class="strike"
          >Give the reason in Reasoning, then
            <button
              type="button"
              class="btn btn-sm"
              :disabled="!reasoning.trim()"
              @click="strike"
            >Strike</button></span>
          <span class="sp" />
          <button
            type="button"
            class="link"
            @click="next"
          >
            Next unjudged →
          </button>
        </div>
      </template>
    </div>
    <p
      v-else
      class="hint"
    >
      Select a stressor to judge it on the picture of {{ name }}.
    </p>
  </section>
</template>

<style scoped>
.judge { font-size: 12.5px; }
.cap { display: flex; align-items: center; gap: 8px; padding: 8px 10px; color: var(--text-2); }
.sp { flex: 1; }
.tbl { width: 100%; border-collapse: collapse; }
.tbl th { text-align: left; font-size: 11px; text-transform: uppercase; color: var(--muted); padding: 4px 8px; }
.jr { cursor: pointer; }
.jr td { padding: 5px 8px; border-top: 1px solid var(--border); vertical-align: top; }
.jr.sel td { background: var(--accent-soft); }
.jr.sel { outline: 2px solid var(--accent); outline-offset: -2px; }
.jr.off td { color: var(--faint); text-decoration: line-through; }
.rid { font-family: ui-monospace, monospace; color: var(--text-2); width: 3em; }
.v { color: var(--text-2); width: 6em; }
.focus { border-top: 1px solid var(--border); padding: 8px 10px; display: grid; gap: 8px; }
.what { margin: 0; }
.struck { margin: 0; color: var(--muted); display: flex; gap: 8px; align-items: center; }
.verdicts { display: flex; gap: 6px; }
.why { display: grid; gap: 3px; font-size: 11.5px; color: var(--muted); }
.cell-in { font: inherit; font-size: 12.5px; padding: 3px 6px; }
.acts { display: flex; align-items: center; gap: 8px; }
.link { border: none; background: none; padding: 0; font: inherit; color: var(--accent-strong); cursor: pointer; }
.link:hover { text-decoration: underline; }
.strike { color: var(--muted); }
.hint { padding: 6px 10px 10px; margin: 0; color: var(--muted); }
</style>
