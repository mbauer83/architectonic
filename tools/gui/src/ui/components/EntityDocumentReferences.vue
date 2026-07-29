<script setup lang="ts">
/** "Referenced in documents" list for the entity detail view. Pure display. */
import type { EntityDetail } from '../../domain'

defineProps<{ references: NonNullable<EntityDetail['referenced_in_documents']> }>()
</script>

<template>
  <div class="card document-reference-card">
    <h2 class="section-title">
      Referenced in documents
    </h2>
    <ul class="document-reference-list">
      <li
        v-for="docRef in references"
        :key="`${docRef.document_id}:${docRef.section}:${docRef.href}`"
        class="document-reference-item"
      >
        <RouterLink
          :to="{ path: `/documents/${encodeURIComponent(docRef.document_id)}` }"
          class="document-reference-title"
        >
          {{ docRef.title }}
        </RouterLink>
        <span class="document-reference-meta">
          {{ docRef.doc_type }}<template v-if="docRef.section"> · {{ docRef.section }}</template>
        </span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; }
.document-reference-card { padding: 14px 16px; margin-bottom: 24px; }
.section-title { font-size: 14px; font-weight: 700; margin: 0 0 10px; color: #111827; }
.document-reference-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.document-reference-item { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.document-reference-title { font-size: 13px; font-weight: 600; color: #1d4ed8; }
.document-reference-meta { font-size: 12px; color: #64748b; }
</style>
