<script setup lang="ts">
/** Per-occurrence accept/reject review for a rendered layered/motivation-support result's
 * derived candidates: certain pre-accepted, potential pre-rejected, with type/certainty/
 * witness chain visible at decision time — nothing here persists; accept/reject only
 * changes what the parent's graph currently renders. */
import type { ConnectionItemSummary } from '../../domain'
import { candidateKeyFor, decisionFor, type CandidateReviewState } from '../../domain/derivedCandidateReview'
import { CERTAINTY_LABELS } from '../lib/viewpointStyleTokens'

defineProps<{ candidates: readonly ConnectionItemSummary[]; review: CandidateReviewState }>()
const emit = defineEmits<{
  toggle: [connection: ConnectionItemSummary]
  explain: [connection: ConnectionItemSummary]
  materialize: [connection: ConnectionItemSummary]
}>()
</script>

<template>
  <div
    v-if="candidates.length > 0"
    class="candidate-panel"
  >
    <h3>Derived candidates</h3>
    <ul class="candidate-list">
      <li
        v-for="candidate in candidates"
        :key="candidateKeyFor(candidate)"
        class="candidate-row"
      >
        <span class="candidate-type">{{ candidate.type.replace('archimate-', '') }}</span>
        <span
          class="candidate-certainty"
          :class="`certainty--${candidate.certainty}`"
        >{{ candidate.certainty ? CERTAINTY_LABELS[candidate.certainty] : '' }}</span>
        <span
          v-if="candidate.hops !== null"
          class="candidate-hops"
        >{{ candidate.hops }} hop{{ candidate.hops === 1 ? '' : 's' }}</span>
        <button
          class="decision-btn"
          :class="{ 'decision-btn--accepted': decisionFor(review, candidateKeyFor(candidate)) === 'accepted' }"
          @click="emit('toggle', candidate)"
        >
          {{ decisionFor(review, candidateKeyFor(candidate)) === 'accepted' ? 'Accepted' : 'Rejected' }}
        </button>
        <button
          class="link-btn"
          @click="emit('explain', candidate)"
        >
          Explain
        </button>
        <button
          class="link-btn"
          @click="emit('materialize', candidate)"
        >
          Materialize
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.candidate-panel { padding: 10px 16px; border-bottom: 1px solid #e5e7eb; font-size: 12.5px; }
.candidate-panel h3 { margin: 0 0 6px; font-size: 12.5px; color: #374151; }
.candidate-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 4px; }
.candidate-row { display: flex; align-items: center; gap: 8px; }
.candidate-type { font-family: monospace; color: #374151; }
.candidate-certainty { padding: 1px 6px; border-radius: 4px; font-size: 11px; }
.certainty--certain { background: #dcfce7; color: #166534; }
.certainty--potential { background: #fef3c7; color: #92400e; }
.candidate-hops { color: #6b7280; font-size: 11px; }
.decision-btn { padding: 2px 8px; border-radius: 4px; border: 1px solid #d1d5db; background: #fee2e2; color: #991b1b; font-size: 11px; cursor: pointer; }
.decision-btn--accepted { background: #dcfce7; color: #166534; }
.link-btn { border: none; background: none; color: #2563eb; font-size: 11px; cursor: pointer; padding: 0; }
</style>
