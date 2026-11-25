<script setup lang="ts">
/**
 * The confirmation for *Apply to the model…*: what the dry run says would be written, what is skipped
 * because the model already holds it, and the refusal when there is one — in the server's words. The
 * apply runs only from here, and writes every operation in one write or none. The page that owns the
 * apply (`useCandidateApply`) is told it was applied: this confirmation is gone by then.
 */
import { computed } from 'vue'
import { canApply, operationLabel, previewSentence } from '../../../domain/candidates/candidateApply'
import type { CandidateApply } from '../../composables/useCandidateApply'

const props = defineProps<{ apply: CandidateApply; name: string }>()

const preview = computed(() => props.apply.preview.value)
</script>

<template>
  <section
    v-if="preview"
    class="apply card"
    aria-label="Apply to the model"
    data-testid="apply-candidate"
  >
    <header>
      <b>Apply {{ name }} to the model</b>
      <span>{{ previewSentence(preview) }}</span>
    </header>
    <p
      v-if="preview.refusal"
      class="refusal"
      role="alert"
      data-testid="apply-refusal"
    >
      {{ preview.refusal }}
    </p>
    <ul v-if="preview.writes.length">
      <li
        v-for="(one, index) in preview.writes"
        :key="`w${index}`"
      >
        <span :class="`standing standing--${one.standing}`">{{ one.standing }}</span>
        {{ operationLabel(one.operation) }} <small>{{ one.reason }}</small>
      </li>
    </ul>
    <ul
      v-if="preview.skipped.length"
      class="skipped"
    >
      <li
        v-for="(one, index) in preview.skipped"
        :key="`s${index}`"
      >
        <span class="standing">skipped</span> {{ operationLabel(one.operation) }} <small>{{ one.reason }}</small>
      </li>
    </ul>
    <p
      v-if="apply.error.value"
      class="refusal"
      role="alert"
    >
      {{ apply.error.value }}
    </p>
    <footer>
      <button
        type="button"
        class="btn btn-sm btn-primary"
        data-testid="apply-confirm"
        :disabled="!canApply(preview) || apply.busy.value"
        @click="apply.confirm()"
      >
        Apply
      </button>
      <button
        type="button"
        class="btn btn-sm"
        @click="apply.close()"
      >
        Cancel
      </button>
    </footer>
  </section>
</template>

<style scoped>
.apply { margin: 6px 0 10px; padding: 8px 10px; font-size: 12.5px; }
header { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; color: var(--text); }
header span { color: var(--muted); }
ul { margin: 6px 0 0; padding-left: 18px; color: var(--text); }
li { margin: 2px 0; }
li small { color: var(--muted); }
.skipped { color: var(--muted); }
.standing { font-size: 11px; font-weight: 600; padding: 0 5px; border-radius: 3px; background: var(--soft); }
.standing--conflicting, .standing--drifted { color: var(--danger-strong); }
.refusal { color: var(--danger-strong); margin: 6px 0 0; }
footer { display: flex; gap: 8px; margin-top: 8px; }
</style>
