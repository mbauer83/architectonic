<script setup lang="ts">
/**
 * One architecture's standing against a test set, in one quiet line: "Residuality +0.33 · survives 8
 * of 12 (naive 4)", or how many are judged while some are not. The strict figure, counting full
 * survivals only, is on hover. Read on the analysis workspace, and on the candidate and compare pages.
 */
import { computed } from 'vue'
import type { ArchitectureStanding } from '../../../domain/schemas/stressEvaluation'
import { residualityDetail, residualityLine } from '../../../domain/stressAnalysis/testSet'

const props = defineProps<{ standing: ArchitectureStanding; label?: string }>()
const line = computed(() => residualityLine(props.standing))
</script>

<template>
  <p
    class="residuality"
    :title="residualityDetail(standing)"
    data-testid="residuality"
  >
    <slot name="who">
      <span class="who">{{ label }}</span>
    </slot>
    <span :class="{ figure: standing.residuality !== undefined }">{{ line }}</span>
    <slot />
  </p>
</template>

<style scoped>
.residuality { display: flex; gap: 8px; align-items: baseline; margin: 0; font-size: 12px; color: var(--muted); }
.who { color: var(--text-2); }
.figure { color: var(--text-2); font-variant-numeric: tabular-nums; }
</style>
