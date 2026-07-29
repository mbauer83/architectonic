<script setup lang="ts">
/**
 * Review step of the STPA wizard: reports the coverage checks that still fail and gates
 * baseline sealing on all of them passing.
 */

import type { StpaCompleteSummary } from '../views/AssuranceStpaWizard.helpers'

defineProps<{
  summary: StpaCompleteSummary | null
  busy: boolean
}>()

const emit = defineEmits<{ recheck: []; seal: [] }>()
</script>

<template>
  <section class="step-body">
    <button
      class="add-btn"
      type="button"
      :disabled="busy"
      @click="emit('recheck')"
    >
      ↺ Re-check completeness
    </button>
    <div
      v-if="summary"
      class="review"
    >
      <p
        class="review-status"
        :class="summary.passed ? 'review-status--ok' : 'review-status--gap'"
      >
        {{ summary.passed ? 'All STPA coverage checks passed.' : 'Coverage gaps remain:' }}
      </p>
      <ul
        v-if="!summary.passed"
        class="gap-list"
      >
        <li
          v-for="f in summary.failed"
          :key="f.key"
        >
          {{ f.key }} — {{ f.gapCount }} gap{{ f.gapCount === 1 ? '' : 's' }}
        </li>
      </ul>
      <button
        class="seal-btn"
        type="button"
        :disabled="busy || !summary.passed"
        @click="emit('seal')"
      >
        Seal baseline
      </button>
      <p
        v-if="!summary.passed"
        class="seal-note"
      >
        Resolve the gaps above (add the missing links in the relevant steps or the
        node browser) before sealing.
      </p>
    </div>
  </section>
</template>

<style scoped>
.step-body { display: flex; flex-direction: column; gap: 12px; }
.add-btn {
  align-self: flex-start; font-size: 13px; padding: 7px 14px; border: none; border-radius: 6px;
  background: #2563eb; color: #fff; font-weight: 600; cursor: pointer;
}
.add-btn:disabled { opacity: 0.5; cursor: default; }
.review { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
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
