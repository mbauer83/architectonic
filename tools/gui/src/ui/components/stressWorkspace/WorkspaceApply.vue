<script setup lang="ts">
/**
 * *Apply…* from the workspace (06·8): the analysis answers first with what is left — the same sentences
 * as *What is left*, each a link to its row — and then with the candidate's dry run, in the candidate
 * page's own confirmation (`ApplyCandidate`). What is left informs and never blocks: the analysis may
 * be applied incomplete, knowingly. Any draft in the analysis's stack can be applied; the one read on
 * the left is offered first.
 */
import { computed, ref } from 'vue'
import { whatIsLeft, type LeftItem, type WorkspaceTab } from '../../../domain/stressAnalysis/analysisProgress'
import type { ModelService } from '../../../application/ModelService'
import type { Candidates } from '../../composables/useCandidates'
import { useCandidateApply } from '../../composables/useCandidateApply'
import type { StressAnalysis } from '../../composables/useStressAnalysis'
import ApplyCandidate from '../candidates/ApplyCandidate.vue'

const props = defineProps<{
  svc: Pick<ModelService, 'applyCandidate'>; analysis: StressAnalysis; candidates: Candidates
}>()
const emit = defineEmits<{ open: [tab: WorkspaceTab, row: string]; applied: [name: string] }>()

const open = ref(false)
const apply = useCandidateApply(props.svc)
const left = computed(() => props.analysis.progress.value ? whatIsLeft(props.analysis.progress.value.progress) : [])
const drafts = computed(() => props.candidates.inStack.value.filter((one) => one.state === 'draft'))
const chosen = ref('')
const candidate = computed(() => drafts.value.find((one) => one.id === chosen.value) ?? null)

const show = () => {
  open.value = !open.value
  apply.close()
  const read = props.candidates.selected.value
  chosen.value = drafts.value.some((one) => one.id === read) ? read ?? '' : drafts.value.at(-1)?.id ?? ''
}
const close = () => {
  open.value = false
  apply.close()
}
const go = (item: LeftItem) => {
  close()
  emit('open', item.tab, item.row)
}
const applied = () => {
  const name = candidate.value?.name ?? chosen.value
  close()
  emit('applied', name)
}
</script>

<template>
  <div
    class="wa"
    @keydown.esc.stop="close"
  >
    <button
      type="button"
      class="btn btn-sm"
      data-testid="workspace-apply"
      :aria-expanded="open"
      @click="show"
    >
      Apply…
    </button>
    <div
      v-if="open"
      class="progress-pop wa-pop"
      role="dialog"
      aria-label="Apply from the analysis"
      data-testid="workspace-apply-panel"
    >
      <p v-if="!left.length">
        Nothing is left: every stressor is walked and grouped, and every end state answered.
      </p>
      <template v-else>
        <p class="lead">
          Before applying, {{ left.length }} thing{{ left.length === 1 ? ' is' : 's are' }} left in the analysis.
          Applying does not wait for them.
        </p>
        <ul>
          <li
            v-for="item in left"
            :key="item.key"
          >
            <button
              type="button"
              class="link-btn"
              @click="go(item)"
            >
              {{ item.text }}
            </button>
          </li>
        </ul>
      </template>
      <p
        v-if="!drafts.length"
        class="muted"
      >
        No draft candidate in this analysis is left to apply.
      </p>
      <div
        v-else
        class="choose"
      >
        <label>Apply
          <select
            v-model="chosen"
            data-testid="workspace-apply-candidate"
            @change="apply.close()"
          >
            <option
              v-for="one in drafts"
              :key="one.id"
              :value="one.id"
            >{{ one.name }}{{ one.id === analysis.naiveId.value ? ' (naive architecture)' : '' }}</option>
          </select>
        </label>
        <button
          type="button"
          class="btn btn-sm btn-primary"
          data-testid="workspace-apply-check"
          :disabled="!candidate || apply.busy.value"
          @click="apply.open(chosen)"
        >
          Check what it writes…
        </button>
      </div>
      <ApplyCandidate
        v-if="candidate && apply.preview.value?.candidate === candidate.id"
        :apply="apply"
        :name="candidate.name"
        @applied="applied"
      />
      <p
        v-else-if="apply.error.value"
        class="err"
        role="alert"
      >
        {{ apply.error.value }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.wa { position: relative; }
.wa-pop {
  position: absolute; right: 0; top: calc(100% + 6px); z-index: 20; width: 440px; padding: 10px 12px;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  box-shadow: var(--shadow);
  font-size: 12.5px;
}
.lead { margin: 0 0 6px; }
.muted { color: var(--muted); }
.wa-pop ul { margin: 0 0 8px; padding: 0 0 0 16px; }
.wa-pop li { margin: 0 0 4px; }
.link-btn {
  border: none; background: none; color: var(--accent-strong); cursor: pointer; padding: 0; font: inherit;
  text-align: left;
}
.link-btn:hover { text-decoration: underline; }
.choose { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; border-top: 1px solid var(--border); padding-top: 8px; }
.choose select { margin-left: 4px; max-width: 220px; }
.err { color: var(--danger-strong); }
</style>
