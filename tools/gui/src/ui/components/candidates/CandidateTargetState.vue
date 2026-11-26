<script setup lang="ts">
/**
 * A candidate's target state on its page: the band saying it stands in the model beside the baseline, with
 * its plateaus and gap linked and *Move into the baseline…*, and the confirmation for either write — what
 * the dry run says would be written and the refusal, in the server's words. An edit is read against what the
 * model holds where it writes, as the apply card reads it (`FieldChangeView`). The writes run only from here;
 * the page that owns the candidate (`useCandidateTargetState`) is told one landed.
 */
import { computed } from 'vue'
import {
  moveSentence, targetOperationLines, targetSentence, withdrawSentence,
} from '../../../domain/candidates/candidateTargetState'
import type { CandidateTargetState } from '../../composables/useCandidateTargetState'
import { entityDetailRoute } from '../../router/artifactRoutes'
import PermittedButton from '../PermittedButton.vue'
import { operationsAppliedValues } from '../../../domain/candidates/candidateApply'
import FieldChangeView from './FieldChangeView.vue'

const props = defineProps<{ target: CandidateTargetState; candidateId: string; name: string }>()

const standing = computed(() => props.target.standing.value)
const preview = computed(() => {
  const shown = props.target.preview.value
  return shown?.candidate === props.candidateId ? shown : null
})
const sentence = computed(() => {
  const shown = preview.value
  if (!shown || shown.refusal) return ''
  if (shown.write === 'apply' && shown.ids) return targetSentence(shown.ids, shown.operations.length)
  return shown.write === 'withdraw' ? withdrawSentence(shown.operations.length) : moveSentence(shown.operations.length)
})
const TITLES = {
  apply: (name: string) => `Apply ${name} as a target state`,
  move: (name: string) => `Move ${name} into the baseline`,
  withdraw: (name: string) => `Withdraw the target state of ${name}`,
} as const
const VERBS = { apply: 'Apply as a target state', move: 'Move into the baseline', withdraw: 'Withdraw' } as const
const copies = computed(() => Object.keys(standing.value?.copies ?? {}).length)
const lines = computed(() => {
  const shown = preview.value
  if (!shown) return []
  // Each edit read against what the model holds where it writes, as the apply card reads it.
  const edited = operationsAppliedValues(shown.operations, shown.standing)
  return targetOperationLines(shown.operations, shown.ids ?? standing.value)
    .map((line, index) => ({ line, edited: edited[index] ?? null }))
})
</script>

<template>
  <div
    v-if="standing"
    class="banner target"
    role="status"
    data-testid="target-state"
  >
    <b>In the model as a target state:</b>
    <span>
      beside the baseline, held by the
      <RouterLink :to="entityDetailRoute(standing.target)">Target plateau</RouterLink>,
      with the originals in the
      <RouterLink :to="entityDetailRoute(standing.baseline)">Baseline plateau</RouterLink>
      and a <RouterLink :to="entityDetailRoute(standing.gap)">gap</RouterLink> between them;
      {{ copies }} "(target)" {{ copies === 1 ? 'copy' : 'copies' }}.
    </span>
    <span class="sp" />
    <PermittedButton
      operation="changes_move_candidate_into_baseline"
      class="btn btn-sm"
      data-testid="move-into-baseline"
      :disabled="target.busy.value"
      @click="target.open('move', candidateId)"
    >
      Move into the baseline…
    </PermittedButton>
    <PermittedButton
      operation="changes_withdraw_candidate_target_state"
      class="btn btn-sm"
      data-testid="withdraw-target-state"
      title="Take the target state out of the model instead, leaving the baseline as it was"
      :disabled="target.busy.value"
      @click="target.open('withdraw', candidateId)"
    >
      Withdraw…
    </PermittedButton>
  </div>
  <section
    v-if="preview"
    class="apply card"
    :aria-label="VERBS[preview.write]"
    data-testid="target-state-confirm"
  >
    <header>
      <b>{{ TITLES[preview.write](name) }}</b>
      <span>{{ sentence }}</span>
    </header>
    <p
      v-if="preview.refusal"
      class="refusal"
      role="alert"
      data-testid="target-state-refusal"
    >
      {{ preview.refusal }}
    </p>
    <p
      v-if="preview.unheld.length"
      class="note"
    >
      A plateau may not aggregate {{ preview.unheld.join(', ') }}; those stand in their state without one.
    </p>
    <details v-if="preview.operations.length && !preview.refusal">
      <summary>The {{ preview.operations.length }} operations</summary>
      <ul>
        <li
          v-for="(one, index) in lines"
          :key="index"
        >
          {{ one.line }}
          <FieldChangeView
            v-if="one.edited"
            class="edit"
            :before="one.edited.before"
            :after="one.edited.after"
          />
        </li>
      </ul>
    </details>
    <p
      v-if="target.error.value"
      class="refusal"
      role="alert"
    >
      {{ target.error.value }}
    </p>
    <footer>
      <button
        type="button"
        class="btn btn-sm btn-primary"
        data-testid="target-state-confirm-write"
        :disabled="!!preview.refusal || target.busy.value"
        @click="target.confirm()"
      >
        {{ VERBS[preview.write] }}
      </button>
      <button
        type="button"
        class="btn btn-sm"
        @click="target.close()"
      >
        Cancel
      </button>
    </footer>
  </section>
</template>

<style scoped>
.banner { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; margin: 6px 0 10px; padding: 8px 10px;
  font-size: 12.5px; border-radius: 4px; background: var(--accent-soft); color: var(--text); }
.banner .sp { flex: 1; }
.apply { margin: 6px 0 10px; padding: 8px 10px; font-size: 12.5px; }
header { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; color: var(--text); }
header span { color: var(--muted); }
details { margin-top: 6px; color: var(--text); }
ul { margin: 4px 0 0; padding-left: 18px; }
li { margin: 2px 0; }
.edit { display: block; margin: 2px 0 4px; }
.note { color: var(--muted); margin: 6px 0 0; }
.refusal { color: var(--danger-strong); margin: 6px 0 0; }
footer { display: flex; gap: 8px; margin-top: 8px; }
</style>
