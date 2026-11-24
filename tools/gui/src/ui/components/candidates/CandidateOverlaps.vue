<script setup lang="ts">
/**
 * What the server's integration check found between candidates (`changes_check_candidates`): each
 * overlap — the same element, field or relation touched by more than one, or one removing what
 * another uses — with its parties and their operations. Shared by a stress analysis's Integration tab
 * and the candidate comparison, so an overlap reads the same on both.
 */
import type { IntegrationCheck } from '../../../domain/schemas/candidates'

defineProps<{
  check: IntegrationCheck
  /** An element or relation by name. */
  nameOf: (id: string) => string
  /** A candidate by name. */
  nameOfSet: (id: string) => string
  /** What is said when nothing overlaps. */
  noneText: string
}>()

const operationWords = (operation: Readonly<Record<string, unknown>>): string =>
  [operation.op, operation.field, operation.value].filter((part) => part !== undefined).map(String).join(' · ')
</script>

<template>
  <div data-testid="candidate-overlaps">
    <div
      v-for="(overlap, index) in check.overlaps"
      :key="index"
      class="conf"
    >
      <h4>{{ overlap.kind }}: {{ nameOf(overlap.subject) }}</h4>
      <div class="sides">
        <div
          v-for="party in overlap.parties"
          :key="party.set_id"
          class="side"
        >
          <small>{{ nameOfSet(party.set_id) }}</small>
          {{ operationWords(party.operation) }}
        </div>
      </div>
    </div>
    <p
      v-if="!check.overlaps.length"
      class="none"
    >
      {{ noneText }}
    </p>
  </div>
</template>

<style scoped>
.conf { border: 1px solid var(--border); border-radius: 8px; margin: 8px 0; padding: 8px 10px; }
.conf h4 { font-size: 13px; margin: 0 0 4px; }
.sides { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 8px; }
.side { border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; }
.side small { display: block; color: var(--muted); font-size: 11px; }
.none { color: var(--text-2); margin: 0 0 8px; }
</style>
