<script setup lang="ts">
/**
 * A candidate's core idea in a sentence or two (its `description`), where the candidate is read: shown under its
 * name, and — where the reader may change it — written in place with *Describe…* or *Edit*. Distinct from the
 * rationale, the longer argument for it, which this does not show. Saved through the candidate's versioned edit.
 */
import { computed, nextTick, ref } from 'vue'
import { DESCRIPTION_LIMIT, type CandidateSummary } from '../../../domain/schemas/candidates'
import type { Candidates } from '../../composables/useCandidates'
import PermittedButton from '../PermittedButton.vue'

const props = defineProps<{ candidates: Pick<Candidates, 'describe'>; summary: CandidateSummary; editable?: boolean }>()

const editing = ref(false)
const draft = ref('')
const saving = ref(false)
const field = ref<HTMLTextAreaElement | null>(null)
const left = computed(() => DESCRIPTION_LIMIT - draft.value.length)

const begin = async () => {
  draft.value = props.summary.description
  editing.value = true
  await nextTick()
  field.value?.focus()
}
const save = async () => {
  saving.value = true
  if (await props.candidates.describe(props.summary.id, draft.value.trim())) editing.value = false
  saving.value = false
}
</script>

<template>
  <form
    v-if="editing"
    class="describe"
    data-testid="candidate-description-form"
    @submit.prevent="save"
    @keydown.esc.stop.prevent="editing = false"
  >
    <label>Core idea, in a sentence or two
      <textarea
        ref="field"
        v-model="draft"
        rows="2"
        :maxlength="DESCRIPTION_LIMIT"
        data-testid="candidate-description-input"
      /></label>
    <span class="acts">
      <small :class="{ low: left < 30 }">{{ left }} characters left</small>
      <button
        type="submit"
        class="btn btn-sm btn-primary"
        :disabled="saving"
      >Save</button>
      <button
        type="button"
        class="btn btn-sm"
        @click="editing = false"
      >Cancel</button>
    </span>
  </form>
  <p
    v-else-if="summary.description || editable"
    class="desc"
    data-testid="candidate-description"
  >
    <span v-if="summary.description">{{ summary.description }}</span>
    <span
      v-else
      class="none"
    >No description of its core idea yet.</span>
    <PermittedButton
      v-if="editable"
      operation="changes_edit_candidate"
      class="link"
      data-testid="describe-candidate"
      @click="begin"
    >
      {{ summary.description ? 'Edit' : 'Describe…' }}
    </PermittedButton>
  </p>
</template>

<style scoped>
.desc { margin: 2px 0 0; font-size: 12.5px; color: var(--text-2); font-style: italic; }
.desc .none { color: var(--muted); }
.link {
  font: inherit; font-style: normal; font-size: 11.5px; margin-left: 6px; padding: 0; border: none; background: none;
  color: var(--accent-strong); cursor: pointer;
}
.link:hover { text-decoration: underline; }
.describe { display: flex; flex-direction: column; gap: 4px; margin: 4px 0 0; font-size: 12px; }
.describe label { display: flex; flex-direction: column; gap: 2px; color: var(--muted); }
.describe textarea { font: inherit; font-size: 12.5px; color: var(--text); resize: vertical; }
.acts { display: flex; gap: 6px; align-items: center; justify-content: flex-end; }
.acts small { color: var(--muted); margin-right: auto; }
.acts small.low { color: var(--warn-text); }
</style>
