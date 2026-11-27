<script setup lang="ts">
/**
 * The open advice on what a promotion would carry. Shown in the dry run so the promotion is made
 * knowingly, and never blocking: advice is a heuristic that may be a deliberate choice, which is why it
 * sits apart from the schema errors that do stop a promotion.
 */

import type { VerificationIssue } from '../../domain/schemas/write-results'
import { entityDetailRoute } from '../router/artifactRoutes'

defineProps<{ advice: readonly VerificationIssue[] }>()

const subjectOf = (issue: VerificationIssue): string | null => {
  const subject = issue.details?.artifact_id
  return typeof subject === 'string' ? subject : null
}
</script>

<template>
  <div
    v-if="advice.length"
    class="advice-box"
    data-testid="promotion-advice"
  >
    <h3 class="section-title">
      Advice on what is promoted
    </h3>
    <p class="advice-note">
      Modelling heuristics that may be deliberate. They do not block the promotion; accept one on the
      element's page, with a reason, to quiet it.
    </p>
    <ul class="advice-items">
      <li
        v-for="issue in advice"
        :key="`${issue.code}-${subjectOf(issue)}`"
        class="advice-item"
      >
        <code class="advice-code">{{ issue.code }}</code>
        <RouterLink
          v-if="subjectOf(issue)"
          :to="{ path: entityDetailRoute(subjectOf(issue) ?? '') }"
          class="advice-message"
        >
          {{ issue.message }}
        </RouterLink>
        <span
          v-else
          class="advice-message"
        >{{ issue.message }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.advice-box { border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; }
.section-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--text-2); margin-bottom: 8px; }
.advice-note { font-size: 12px; color: var(--muted); margin: 0 0 8px; }
.advice-items { list-style: none; display: flex; flex-direction: column; gap: 6px; padding: 0; }
.advice-item { display: flex; gap: 8px; align-items: baseline; font-size: 12px; }
.advice-code { font-size: 11px; color: var(--muted); }
.advice-message { color: var(--text); }
</style>
