<script setup lang="ts">
/** GRC wizard's "Coverage" step: the §9 anti-subordination safeguard note, a re-checkable
 * completeness summary, and the seal-baseline action (blocked until coverage passes). */
import { inject } from 'vue'
import { ANTI_SUBORDINATION_NOTE } from '../views/AssuranceGrcWizard.helpers'
import { grcWizardDataKey } from '../composables/useGrcWizardData'

const data = inject(grcWizardDataKey)!
</script>

<template>
  <section class="step-body">
    <p class="safeguard">
      {{ ANTI_SUBORDINATION_NOTE }}
    </p>
    <button
      class="add-btn"
      type="button"
      :disabled="data.busy"
      @click="data.loadCompleteness"
    >
      ↺ Re-check coverage
    </button>
    <div
      v-if="data.completenessSummary"
      class="review"
    >
      <p
        class="review-status"
        :class="data.completenessSummary.passed ? 'review-status--ok' : 'review-status--gap'"
      >
        {{ data.completenessSummary.passed ? 'All GRC coverage checks passed.' : 'Coverage gaps remain:' }}
      </p>
      <ul
        v-if="!data.completenessSummary.passed"
        class="gap-list"
      >
        <li
          v-for="f in data.completenessSummary.failed"
          :key="f.key"
        >
          {{ f.key }} — {{ f.gapCount }} gap{{ f.gapCount === 1 ? '' : 's' }}
        </li>
      </ul>
      <button
        class="seal-btn"
        type="button"
        :disabled="data.busy || !data.completenessSummary.passed"
        @click="data.sealBaseline"
      >
        Seal baseline
      </button>
      <p
        v-if="!data.completenessSummary.passed"
        class="seal-note"
      >
        Resolve the gaps above (set treatments and owners, link controls to obligations)
        before sealing.
      </p>
    </div>
  </section>
</template>

<style scoped>
.step-body { display: flex; flex-direction: column; gap: 12px; }
.add-btn {
  font-size: 13px; padding: 7px 14px; border: none; border-radius: 6px;
  background: #2563eb; color: #fff; font-weight: 600; cursor: pointer;
}
.add-btn:disabled { opacity: 0.5; cursor: default; }
.safeguard { font-size: 13px; color: #7c2d12; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; padding: 10px 14px; margin: 0; }
.review { display: flex; flex-direction: column; gap: 10px; margin-top: 4px; }
.review-status { font-size: 14px; font-weight: 600; margin: 0; }
.review-status--ok { color: #15803d; }
.review-status--gap { color: #b45309; }
.gap-list { margin: 0; padding-left: 20px; font-size: 13px; color: #475569; }
.seal-btn {
  align-self: flex-start; font-size: 13px; padding: 8px 18px; border: none; border-radius: 6px;
  background: #15803d; color: #fff; font-weight: 600; cursor: pointer;
}
.seal-btn:disabled { opacity: 0.5; cursor: default; }
.seal-note { font-size: 12px; color: #94a3b8; margin: 0; }
</style>
