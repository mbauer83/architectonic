<script setup lang="ts">
/**
 * The test set, apart from the design work: collapsed to one line and the residuality of each judged
 * architecture while the analysis is worked, open to write or hold out stressors and to judge. The
 * procedure is stated once and its order shown as progress, never as a gate. An analysis without a
 * test set shows only a link to add one. *Hold out a random third* asks first, in the section itself:
 * Cancel holds the focus and Esc cancels, so a stray Enter moves nothing.
 */
import { computed, nextTick, ref } from 'vue'
import type { Verdict } from '../../../domain/schemas/stressEvaluation'
import { cell } from '../../../domain/stressAnalysis/analysisRows'
import { NAIVE, procedure } from '../../../domain/stressAnalysis/testSet'
import type { Candidates } from '../../composables/useCandidates'
import type { StressAnalysis } from '../../composables/useStressAnalysis'
import type { TestSet } from '../../composables/useTestSet'
import ResidualityLine from '../candidates/ResidualityLine.vue'
import JudgeWalk from './JudgeWalk.vue'
import StressorInput from './StressorInput.vue'

const props = defineProps<{
  analysis: StressAnalysis
  candidates: Candidates
  testSet: TestSet
  /** The test stressor in focus in the judge walk. */
  selected: string | null
}>()
const emit = defineEmits<{ select: [rowId: string | null] }>()

const open = ref(false)
const evaluation = computed(() => props.analysis.evaluation.value)
const held = computed(() => props.analysis.testStressors.value)
const nameOf = (architecture: string): string => architecture === NAIVE
  ? 'Naive architecture'
  : props.candidates.all.value.find((one) => one.id === architecture)?.name ?? architecture
/** Each architecture with a line: the naive, the integration, and every candidate judged so far. */
const standings = computed(() => evaluation.value?.architectures ?? [])
const evaluable = computed(() => props.candidates.inStack.value.filter((one) => one.id !== props.analysis.naiveId.value
  && !standings.value.some((standing) => standing.architecture === one.id)))
const steps = computed(() => (evaluation.value ? procedure(evaluation.value.stage) : []))
const design = computed(() => evaluation.value?.design_stressors ?? 0)

const judge = (architecture: string) => {
  open.value = true
  props.testSet.judgeOn(architecture)
  emit('select', held.value[0]?.row_id ?? null)
}
/** A judgement in the walk, of the architecture being judged. */
const judgeOne = (stressor: string, cells: Readonly<{ verdict?: Verdict; usable?: boolean; reasoning?: string }>) => {
  const architecture = props.testSet.judging.value
  if (architecture) void props.testSet.judge(stressor, architecture, cells)
}
/** Whether the hold-out is being asked about; its Cancel takes the focus. */
const asking = ref(false)
const cancelHold = ref<HTMLButtonElement | null>(null)
const askHoldOut = async () => {
  asking.value = true
  await nextTick()
  cancelHold.value?.focus()
}
const holdOut = async () => {
  asking.value = false
  await props.testSet.holdOut()
}
</script>

<template>
  <section
    class="test-set"
    :class="{ card: held.length || open }"
    data-testid="test-set"
  >
    <button
      v-if="!held.length && !open"
      type="button"
      class="add"
      data-testid="add-test-set"
      @click="open = true"
    >
      Add a test set
    </button>
    <template v-else>
      <button
        type="button"
        class="head"
        :aria-expanded="open"
        @click="open = !open"
      >
        <b>Test set</b>
        <span class="n">{{ held.length }} stressor{{ held.length === 1 ? '' : 's' }} held apart</span>
        <ol
          class="steps"
          aria-label="Procedure"
        >
          <li
            v-for="step in steps"
            :key="step.label"
            :class="{ done: step.done }"
          >
            {{ step.label }}
          </li>
        </ol>
        <span
          class="caret"
          aria-hidden="true"
        >{{ open ? '▴' : '▾' }}</span>
      </button>
      <div
        v-if="held.length"
        class="lines"
      >
        <ResidualityLine
          v-for="standing in standings"
          :key="standing.architecture"
          :standing="standing"
          :label="standing.integrated ? `${nameOf(standing.architecture)} (integrated)` : nameOf(standing.architecture)"
        >
          <button
            v-if="open && testSet.judging.value !== standing.architecture"
            type="button"
            class="link"
            :data-judge="standing.architecture"
            @click="judge(standing.architecture)"
          >
            Judge
          </button>
        </ResidualityLine>
      </div>
      <div
        v-if="open"
        class="body"
      >
        <p class="procedure">
          Kept apart from the design work: write it or hold it out before adapting, do not adapt against it,
          and judge it at the end — the naive architecture first, the integration last.
        </p>
        <JudgeWalk
          v-if="testSet.judging.value"
          :architecture="testSet.judging.value"
          :name="nameOf(testSet.judging.value)"
          :stressors="held"
          :verdicts="analysis.verdicts.value"
          :selected="selected"
          :saving="analysis.saving.value"
          @select="emit('select', $event)"
          @judge="judgeOne"
          @restore="testSet.restore"
          @done="testSet.judgeOn(null)"
        />
        <template v-else>
          <StressorInput
            :unwritten="evaluation?.unwritten_perspectives ?? []"
            placeholder="Write a test stressor and press Enter"
            :disabled="analysis.saving.value"
            @write="testSet.write"
          />
          <div class="acts">
            <button
              v-if="design >= 3"
              type="button"
              class="btn btn-sm"
              data-testid="hold-out"
              :disabled="testSet.holding.value || asking"
              @click="askHoldOut"
            >
              Hold out a random third
            </button>
            <label
              v-if="held.length && evaluable.length"
              class="evaluate"
            >Evaluate against the test set
              <select
                value=""
                data-testid="evaluate-candidate"
                @change="judge(($event.target as HTMLSelectElement).value)"
              >
                <option value="">a candidate…</option>
                <option
                  v-for="one in evaluable"
                  :key="one.id"
                  :value="one.id"
                >{{ one.name }}</option>
              </select>
            </label>
          </div>
          <div
            v-if="asking"
            class="ask"
            role="alertdialog"
            aria-label="Hold out a random third"
            data-testid="hold-out-ask"
            @keydown.esc.stop.prevent="asking = false"
          >
            <p>
              Move {{ Math.floor(design / 3) }} of the {{ design }} design stressors, chosen at random, into the
              test set? It is best done before they are walked.
            </p>
            <div class="ask-acts">
              <button
                ref="cancelHold"
                type="button"
                class="btn btn-sm"
                @click="asking = false"
              >
                Cancel
              </button>
              <button
                type="button"
                class="btn btn-sm btn-primary"
                data-testid="hold-out-confirm"
                @click="holdOut"
              >
                Hold out {{ Math.floor(design / 3) }}
              </button>
            </div>
          </div>
          <ul class="held">
            <li
              v-for="row in held"
              :key="row.row_id"
            >
              <span class="rid">{{ row.row_id }}</span> {{ cell(row, 'stressor') }}
            </li>
          </ul>
        </template>
      </div>
    </template>
  </section>
</template>

<style scoped>
.test-set { margin-top: 10px; font-size: 12.5px; }
.add, .link { border: none; background: none; padding: 0; font: inherit; color: var(--accent-strong); cursor: pointer; }
.add { font-size: 12px; color: var(--muted); }
.add:hover, .link:hover { text-decoration: underline; color: var(--accent-strong); }
.head {
  display: flex; gap: 10px; align-items: baseline; width: 100%; border: none; background: none; padding: 8px 10px;
  font: inherit; color: var(--text-2); cursor: pointer; text-align: left; flex-wrap: wrap;
}
.n { flex: 1; color: var(--muted); }
.steps {
  display: flex; flex-wrap: wrap; flex-basis: 100%; order: 3; gap: 2px 6px; margin: 0; padding: 0; list-style: none;
  font-size: 11.5px; color: var(--faint);
}
.steps li { white-space: nowrap; }
.steps li + li::before { content: '→ '; color: var(--faint); }
.steps li.done { color: var(--ok-text); }
.steps li.done::after { content: ' ✓'; }
.caret { color: var(--muted); }
.lines { display: grid; gap: 2px; padding: 0 10px 8px; }
.body { border-top: 1px solid var(--border); }
.procedure { margin: 0; padding: 8px 10px 0; color: var(--muted); font-size: 12px; }
.acts { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; padding: 4px 10px; }
.evaluate { font-size: 12px; color: var(--muted); }
.evaluate select { font: inherit; margin-left: 4px; max-width: 220px; }
.ask {
  margin: 4px 10px 6px; padding: 8px 10px; border: 1px solid var(--accent-border); border-radius: 6px;
  background: var(--accent-soft); color: var(--text);
}
.ask p { margin: 0 0 6px; }
.ask-acts { display: flex; gap: 8px; justify-content: flex-end; }
.held { margin: 4px 0 8px; padding: 0 10px 0 28px; color: var(--text-2); }
.held li { margin: 2px 0; }
.rid { font-family: ui-monospace, monospace; color: var(--muted); margin-right: 4px; }
</style>
