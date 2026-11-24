<script setup lang="ts">
/** Renders a matrix-type diagram's pre-rendered markdown tables. Pure display. */
defineProps<{ html: string }>()
</script>

<template>
  <div
    class="matrix-view"
    v-html="html"
  />
</template>

<style scoped>
.matrix-view {
  overflow: auto;
  max-height: clamp(420px, 72vh, 880px);
  padding: 16px;
  background: var(--surface);
  border-radius: 8px;
  border: 1px solid var(--border);
}
.matrix-view :deep(table) { border-collapse: collapse; margin-bottom: 20px; }
.matrix-view :deep(th) {
  border: 1px solid var(--border);
  padding: 6px 8px;
  font-size: 11px;
  font-weight: 600;
  min-width: 5rem;
  max-width: 9rem;
  text-align: center;
  vertical-align: bottom;
  white-space: normal;
  overflow-wrap: break-word;
  word-break: normal;
}
.matrix-view :deep(th:first-child) {
  position: sticky;
  left: 0;
  z-index: 2;
  text-align: left;
  min-width: 11rem;
  max-width: 18rem;
  background: var(--surface);
  border-right: 2px solid var(--border-strong);
}
.matrix-view :deep(td) { border: 1px solid var(--border); padding: 4px 8px; font-size: 12px; }
.matrix-view :deep(td:first-child) {
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--surface);
  font-size: 11px;
  font-weight: 500;
  min-width: 11rem;
  max-width: 18rem;
  overflow-wrap: break-word;
  word-break: normal;
  border-right: 2px solid var(--border-strong);
}
.matrix-view :deep(td:not(:first-child)) { text-align: center; }
.matrix-view :deep(h2) { font-size: 13px; font-weight: 700; margin: 16px 0 6px; color: var(--text-2); }
</style>
