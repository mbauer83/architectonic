<script setup lang="ts">
/**
 * A candidate's target state on its page: the band saying it stands in the model beside the baseline, with
 * its plateaus and gap linked and *Move into the baseline…*, and the confirmation for either write — what
 * the dry run says would be written and the refusal, in the server's words. The writes run only from here;
 * the page that owns the candidate (`useCandidateTargetState`) is told one landed.
 */
import { computed } from 'vue'
import { moveSentence, targetOperationLines, targetSentence } from '../../../domain/candidates/candidateTargetState'
import type { CandidateTargetState } from '../../composables/useCandidateTargetState'
import { entityDetailRoute } from '../../router/artifactRoutes'

const props = defineProps<{ target: CandidateTargetState; candidateId: string; name: string }>()

const standing = computed(() => props.target.standing.value)
const preview = computed(() => {
  const shown = props.target.preview.value
  return shown?.candidate === props.candidateId ? shown : null
})
const sentence = computed(() => {
  const shown = preview.value
  if (!shown || shown.refusal) return ''
  return shown.write === 'apply' && shown.ids
    ? targetSentence(shown.ids, shown.operations.length)
    : moveSentence(shown.operations.length)
})
const copies = computed(() => Object.keys(standing.value?.copies ?? {}).length)
const lines = computed(() => preview.value
  ? targetOperationLines(preview.value.operations, preview.value.ids ?? standing.value)
  : [])
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
    <button
      type="button"
      class="btn btn-sm"
      data-testid="move-into-baseline"
      :disabled="target.busy.value"
      @click="target.open('move', candidateId)"
    >
      Move into the baseline…
    </button>
  </div>
  <section
    v-if="preview"
    class="apply card"
    :aria-label="preview.write === 'apply' ? 'Apply as a target state' : 'Move into the baseline'"
    data-testid="target-state-confirm"
  >
    <header>
      <b>{{ preview.write === 'apply' ? `Apply ${name} as a target state` : `Move ${name} into the baseline` }}</b>
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
          v-for="(line, index) in lines"
          :key="index"
        >
          {{ line }}
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
        {{ preview.write === 'apply' ? 'Apply as a target state' : 'Move into the baseline' }}
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
.note { color: var(--muted); margin: 6px 0 0; }
.refusal { color: var(--danger-strong); margin: 6px 0 0; }
footer { display: flex; gap: 8px; margin-top: 8px; }
</style>
