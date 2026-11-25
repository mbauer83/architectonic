<script setup lang="ts">
/**
 * What an analysis is, under its title: the kind, its status, how many elements the architecture under
 * evaluation holds and the stored diagram it is drawn on, if any, and the context the evaluation is made in.
 */
import type { StressAnalysis } from '../../composables/useStressAnalysis'

defineProps<{ analysis: StressAnalysis }>()
</script>

<template>
  <div class="meta">
    <span class="badge">stress analysis</span>
    <span class="status">{{ analysis.document.value?.status }}</span>
    <span
      v-if="analysis.naive.value"
      class="mono"
    >naive architecture: {{ analysis.naive.value.view.entities.length }}
      {{ analysis.naive.value.view.entities.length === 1 ? 'element' : 'elements' }}{{ analysis.drawnOn.value
        ? ` · drawn on ${analysis.naive.value.drawing?.name ?? analysis.drawnOn.value}` : '' }}</span>
  </div>
  <p
    v-if="analysis.context.value"
    class="context"
    data-testid="analysis-context"
  >
    Context: {{ analysis.context.value }}
  </p>
</template>

<style scoped>
.meta { display: flex; gap: 10px; align-items: center; margin: 8px 0 2px; font-size: 12px; color: var(--muted); }
.badge { background: var(--accent-soft); color: var(--accent-strong); border-radius: 3px; padding: 2px 8px; }
.mono { font-family: ui-monospace, monospace; }
.context { color: var(--text-2); font-size: 12.5px; margin: 2px 0 10px; white-space: pre-line; }
</style>
