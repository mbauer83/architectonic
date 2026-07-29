<script setup lang="ts">
/**
 * Recording one occurrence judgement against the basis it was made on.
 *
 * Occurrence is the only factor nobody can derive — severity and detectability come from the
 * hazard chain and the detection controls, and return on their own when the model moves. So this is
 * the one place a person's judgement enters the matrix, and it is asked for only where it could
 * change the priority band.
 *
 * The cited facts are shown and the rationale is pre-filled from them; the **value is never
 * pre-filled**, and no member of the scale is presented as a default or a suggestion. Pre-filling a
 * rank would make the judgement the tool's and the rationale the person's, which is backwards.
 *
 * The basis digest travels with the submission because a judgement applies only while what it cited
 * still holds. Filed without it, the assessment is retained and never applies, and the row stays
 * undecidable however carefully it was judged.
 */
import { computed, ref } from 'vue'
import {
  citedFacts,
  factorRequestBody,
  initialDraft,
  isSubmittable,
  recorderErrorMessage,
} from './FmeaOccurrenceRecorder.helpers'
import type { CellView } from '../views/AssuranceFmeaView.helpers'

const props = defineProps<{
  cell: CellView
  scale: readonly string[]
}>()

const emit = defineEmits<{ recorded: []; cancelled: [] }>()

// Asked for rather than assumed: this deployment authenticates nobody, and the backend requires an
// author because a band with no attributable reason is the one that cannot be defended in a review.
// Filling it in with a placeholder would satisfy the validation and defeat its purpose. Remembered
// locally so a returning analyst types it once.
const AUTHOR_KEY = 'arch_assurance_factor_author'

const draft = ref(initialDraft(props.cell, localStorage.getItem(AUTHOR_KEY) ?? ''))
const error = ref('')
const saving = ref(false)

const facts = computed(() => citedFacts(props.cell.occurrence_rationale_draft))
const submittable = computed(() => isSubmittable(draft.value))

async function save() {
  error.value = ''
  saving.value = true
  try {
    const resp = await fetch('/api/assurance/fmea/factor', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(factorRequestBody(props.cell, draft.value)),
    })
    localStorage.setItem(AUTHOR_KEY, draft.value.author.trim())
    if (!resp.ok) {
      const body = await resp.json().catch(() => null) as { errors?: { message: string }[] } | null
      error.value = recorderErrorMessage(resp.status, body)
      return
    }
    emit('recorded')
  } catch {
    error.value = 'The judgement could not be sent. Check the connection and try again.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form
    class="occ"
    @submit.prevent="save"
  >
    <p class="occ__lead">
      How often would this happen? Severity and detectability are already derived; this is the one
      judgement the model cannot make.
    </p>

    <div
      v-if="facts.length"
      class="occ__facts"
    >
      <span class="occ__facts-heading">What the model already knows</span>
      <ul>
        <li
          v-for="fact in facts"
          :key="fact"
        >
          {{ fact }}
        </li>
      </ul>
    </div>

    <label class="occ__row">
      <span>Occurrence</span>
      <select
        v-model="draft.value"
        class="occ__value"
        required
      >
        <!-- No default member: an empty selection is the honest starting state. -->
        <option value="">
          —
        </option>
        <option
          v-for="member in scale"
          :key="member"
          :value="member"
        >
          {{ member }}
        </option>
      </select>
    </label>

    <label class="occ__row">
      <span>Recorded by</span>
      <input
        v-model="draft.author"
        class="occ__value"
        type="text"
        required
      >
    </label>

    <label class="occ__row occ__row--wide">
      <span>Rationale</span>
      <textarea
        v-model="draft.justification"
        class="occ__justification"
        rows="4"
        required
      />
    </label>

    <p
      v-if="error"
      class="occ__error"
      role="alert"
    >
      {{ error }}
    </p>

    <div class="occ__actions">
      <button
        type="button"
        class="occ__cancel"
        @click="emit('cancelled')"
      >
        Cancel
      </button>
      <button
        type="submit"
        class="occ__save"
        :disabled="!submittable || saving"
      >
        Record occurrence
      </button>
    </div>
  </form>
</template>

<style scoped>
.occ { display: grid; gap: 8px; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px;
  background: white; text-align: left; font-size: 12px; }
.occ__lead { margin: 0; color: #4b5563; }
.occ__facts { border-left: 3px solid #e5e7eb; padding-left: 8px; color: #374151; }
.occ__facts-heading { font-weight: 600; }
.occ__facts ul { margin: 4px 0 0; padding-left: 16px; }
.occ__row { display: grid; grid-template-columns: 90px 1fr; gap: 8px; align-items: center; }
.occ__row--wide { align-items: start; }
.occ__value, .occ__justification { padding: 6px; border: 1px solid #d1d5db; border-radius: 5px;
  font: inherit; background: white; }
.occ__error { margin: 0; color: #b91c1c; }
.occ__actions { display: flex; gap: 8px; justify-content: flex-end; }
.occ__actions button { padding: 6px 10px; border-radius: 5px; border: 1px solid #d1d5db;
  background: white; font: inherit; cursor: pointer; }
.occ__save { border-color: #1d4ed8; color: #1d4ed8; font-weight: 600; }
.occ__save:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
