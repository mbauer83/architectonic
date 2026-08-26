<script setup lang="ts">
/** "Thought about in scratchpads" list for the entity detail view. Pure display.
 *
 * The third answer to "where does this appear", beside the document and diagram lists. Its own
 * component for the same reason those are two: the rows differ — a document reference carries where
 * inside the document the link sits, a diagram carries its type, a pad carries neither — and one
 * component switching on which kind it was handed would be a flag changing behaviour.
 *
 * A *pad*, not a note. A note holding a model reference stops being a searchable record — the model
 * answers for that thought instead — so the pad is both what survives indexing and what a reader
 * navigates to.
 */
import type { EntityDetail } from '../../domain'

defineProps<{ references: NonNullable<EntityDetail['referenced_in_scratchpads']> }>()
</script>

<template>
  <div class="card scratchpad-reference-card">
    <h2 class="section-title">
      Thought about in scratchpads
    </h2>
    <ul class="scratchpad-reference-list">
      <li
        v-for="padRef in references"
        :key="padRef.artifact_id"
        class="scratchpad-reference-item"
      >
        <RouterLink
          :to="{ path: `/scratchpads/${encodeURIComponent(padRef.artifact_id)}` }"
          class="scratchpad-reference-title"
        >
          {{ padRef.name }}
        </RouterLink>
        <span
          v-if="padRef.status !== 'active'"
          class="scratchpad-reference-meta"
        >{{ padRef.status }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; }
.scratchpad-reference-card { padding: 14px 16px; margin-bottom: 24px; }
.section-title { font-size: 14px; font-weight: 700; margin: 0 0 10px; color: #111827; }
.scratchpad-reference-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.scratchpad-reference-item { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.scratchpad-reference-title { font-size: 13px; font-weight: 600; color: #1d4ed8; }
.scratchpad-reference-meta { font-size: 12px; color: #64748b; }
</style>
