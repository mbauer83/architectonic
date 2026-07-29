<script setup lang="ts">
/**
 * The elements the architecture graph says no analysis has reached.
 *
 * Beside the worklist rather than behind a navigation, because this is what someone deciding what to
 * analyse next needs, and the decision is made while looking at the matrix. Each entry carries the
 * relationships that make the claim — an element the analysis never named is being put forward on the
 * strength of something the reader did not assert, and "the graph says so" is not checkable.
 *
 * Read from the verification result, not recomputed here: the rule that decides load-bearing lives in
 * one place, and a second implementation in the client would eventually disagree with it.
 */
import { computed, onMounted, ref } from 'vue'
import { GAPS_EXPLANATION, gapSummary, structuralGaps } from './FmeaStructuralGaps.helpers'
import type { VerificationIssue } from './FmeaStructuralGaps.helpers'

const issues = ref<VerificationIssue[]>([])
const loaded = ref(false)

const gaps = computed(() => structuralGaps(issues.value))
const summary = computed(() => gapSummary(gaps.value))

async function load() {
  const resp = await fetch('/api/assurance/verify')
  if (resp.ok) {
    issues.value = ((await resp.json()) as { issues: VerificationIssue[] }).issues
  }
  loaded.value = true
}

onMounted(() => { void load() })
</script>

<template>
  <section
    v-if="loaded"
    class="gaps"
  >
    <h2 class="gaps__title">
      Load-bearing, not analysed
    </h2>
    <p class="gaps__explanation">
      {{ GAPS_EXPLANATION }}
    </p>
    <p class="gaps__summary">
      {{ summary }}
    </p>

    <ul
      v-if="gaps.length"
      class="gaps__list"
    >
      <li
        v-for="gap in gaps"
        :key="gap.elementId"
      >
        <span class="gaps__element">{{ gap.heading }}</span>
        <span
          v-if="gap.subheading"
          class="gaps__id"
        >{{ gap.subheading }}</span>
        <span class="gaps__message">{{ gap.message }}</span>
        <details
          v-if="gap.witness.length"
          class="gaps__witness"
        >
          <summary>What relies on it</summary>
          <ul>
            <li
              v-for="step in gap.witness"
              :key="step"
            >
              {{ step }}
            </li>
          </ul>
        </details>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.gaps { margin-top: 24px; max-width: 90ch; }
.gaps__title { font-size: 15px; margin: 0 0 6px; }
.gaps__explanation { font-size: 13px; color: #4b5563; margin: 0 0 8px; max-width: 78ch; line-height: 1.5; }
.gaps__summary { font-size: 12px; color: #6b7280; margin: 0 0 10px; }
.gaps__list { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px;
  max-height: 420px; overflow-y: auto; }
.gaps__list > li { border-left: 3px solid #e5e7eb; padding-left: 8px; font-size: 12px; }
.gaps__element { display: block; font-weight: 600; }
/* The id is demoted, never dropped: it is what someone quotes when they act on the finding. */
.gaps__id { display: block; font-size: 11px; color: #9ca3af; font-family: monospace; }
.gaps__message { display: block; color: #4b5563; }
.gaps__witness { margin-top: 4px; color: #374151; }
.gaps__witness summary { cursor: pointer; }
.gaps__witness ul { margin: 4px 0 0; padding-left: 16px; }
</style>
