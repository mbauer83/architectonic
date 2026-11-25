<script setup lang="ts">
/**
 * *Abandon…*'s card: giving a candidate up instead of applying it, in one of the two ways the candidate
 * decision keeps. *Reject* sets it aside as a considered alternative that lost, kept with its operations in the
 * record; *Delete* removes it, refused (in the server's words) while something still refers to it. A candidate
 * whose target state is in the model is held by it, so the first step offered is withdrawing that
 * (`CandidateTargetState`'s confirmation, through *target*), after which both are open. The page shows the
 * card when its *Abandon…* is pressed; the card says when it is done with (`close`).
 */
import { computed, ref } from 'vue'
import type { Candidates } from '../../composables/useCandidates'
import type { CandidateTargetState } from '../../composables/useCandidateTargetState'
import PermittedButton from '../PermittedButton.vue'

const props = defineProps<{
  candidates: Candidates; target: CandidateTargetState; candidateId: string; name: string; state: string
}>()
const emit = defineEmits<{ rejected: []; deleted: []; close: [] }>()

const busy = ref(false)
const held = computed(() => props.target.standing.value !== null)
/** Rejecting is a move of the work's state, open to a draft or an offered candidate. */
const rejectable = computed(() => props.state === 'draft' || props.state === 'candidate')

const run = async (step: () => Promise<boolean>, then: () => void) => {
  busy.value = true
  const done = await step()
  busy.value = false
  if (!done) return
  emit('close')
  then()
}
const reject = () => run(() => props.candidates.reject(props.candidateId), () => emit('rejected'))
const remove = () => run(() => props.candidates.remove(props.candidateId), () => emit('deleted'))
const withdraw = () => {
  emit('close')
  void props.target.open('withdraw', props.candidateId)
}
</script>

<template>
  <section
    class="abandon card"
    role="dialog"
    :aria-label="`Abandon ${name}`"
    data-testid="abandon-card"
  >
    <header><b>Abandon {{ name }}</b> <span>Nothing it proposes reaches the model.</span></header>
    <template v-if="held">
      <p>
        Its target state is in the model beside the baseline. Withdraw it first; the candidate is then a draft
        again, and can be rejected or deleted.
      </p>
      <footer>
        <PermittedButton
          operation="changes_withdraw_candidate_target_state"
          class="btn btn-sm btn-primary"
          data-testid="abandon-withdraw"
          :disabled="target.busy.value"
          @click="withdraw"
        >
          Withdraw the target state…
        </PermittedButton>
        <button
          type="button"
          class="btn btn-sm"
          @click="emit('close')"
        >
          Cancel
        </button>
      </footer>
    </template>
    <template v-else>
      <ul>
        <li v-if="rejectable">
          <b>Reject</b> keeps it, with its operations, as a considered alternative that lost.
        </li>
        <li><b>Delete</b> removes it and its operations for good.</li>
      </ul>
      <p
        v-if="candidates.error.value"
        class="refusal"
        role="alert"
      >
        {{ candidates.error.value }}
      </p>
      <footer>
        <PermittedButton
          v-if="rejectable"
          operation="changes_edit_candidate"
          class="btn btn-sm btn-primary"
          data-testid="abandon-reject"
          :disabled="busy"
          @click="reject"
        >
          Reject
        </PermittedButton>
        <PermittedButton
          operation="changes_delete_candidate"
          class="btn btn-sm"
          data-testid="abandon-delete"
          :disabled="busy"
          @click="remove"
        >
          Delete
        </PermittedButton>
        <button
          type="button"
          class="btn btn-sm"
          @click="emit('close')"
        >
          Cancel
        </button>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.abandon { margin: 6px 0 10px; padding: 8px 10px; font-size: 12.5px; color: var(--text); }
header span { color: var(--muted); }
p, ul { margin: 6px 0 0; }
ul { padding-left: 18px; }
.refusal { color: var(--danger-strong); }
footer { display: flex; gap: 8px; margin-top: 8px; }
</style>
