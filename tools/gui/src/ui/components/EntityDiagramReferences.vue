<script setup lang="ts">
/** "Drawn in diagrams" list for the entity detail view. Pure display.
 *
 * The other half of "where does this appear", beside `EntityDocumentReferences`. The two are separate
 * components because they are separate questions with different rows — a document reference carries
 * where *inside* the document the link sits, a diagram either draws the entity or does not — and a
 * single component switching on which kind it was given would be a boolean flag changing behaviour.
 *
 * `status` is shown because a draft diagram drawing an entity is a weaker statement than an active
 * one, and a reader asking where something is used needs to be able to tell.
 */
import type { EntityDetail } from '../../domain'

defineProps<{ references: NonNullable<EntityDetail['referenced_in_diagrams']> }>()
</script>

<template>
  <div class="card diagram-reference-card">
    <h2 class="section-title">
      Drawn in diagrams
    </h2>
    <ul class="diagram-reference-list">
      <li
        v-for="diagramRef in references"
        :key="diagramRef.artifact_id"
        class="diagram-reference-item"
      >
        <RouterLink
          :to="{ path: `/diagrams/${encodeURIComponent(diagramRef.artifact_id)}` }"
          class="diagram-reference-title"
        >
          {{ diagramRef.name }}
        </RouterLink>
        <span class="diagram-reference-meta">
          {{ diagramRef.diagram_type.replace('archimate-', '') }}
          <template v-if="diagramRef.status !== 'active'"> · {{ diagramRef.status }}</template>
        </span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; }
.diagram-reference-card { padding: 14px 16px; margin-bottom: 24px; }
.section-title { font-size: 14px; font-weight: 700; margin: 0 0 10px; color: #111827; }
.diagram-reference-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.diagram-reference-item { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.diagram-reference-title { font-size: 13px; font-weight: 600; color: #1d4ed8; }
.diagram-reference-meta { font-size: 12px; color: #64748b; }
</style>
