<script setup lang="ts">
import { computed } from 'vue'
import { distanceLegend } from '../views/GraphExploreView.helpers'

/** Ring legend for anchored executions: an Anchor chip, one chip per OBSERVED modeled
 * distance (witness-chain lengths — e.g. 1/2/4, never a dense 0..max range), and an
 * explicit chip for unranked nodes (no connecting edge to any anchor). */
const props = defineProps<{
  /** Modeled distances observed in the result (`anchor_modeled_distance` values). */
  depths: readonly number[]
  /** Whether the result contains entities the server left unranked. */
  hasUnranked: boolean
}>()

const entries = computed(() => distanceLegend(props.depths))
</script>

<template>
  <div class="hop-legend">
    <span class="hop-chip hop-chip--anchor">Anchor</span>
    <span
      v-for="entry in entries"
      :key="entry.label"
      class="hop-chip"
      :style="{ background: entry.color }"
    >{{ entry.label }}</span>
    <span
      v-if="hasUnranked"
      class="hop-chip hop-chip--unranked"
    >no path to anchor</span>
  </div>
</template>

<style scoped>
.hop-legend {
  display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
  padding: 6px 16px; background: white; border-bottom: 1px solid #e5e7eb;
}
.hop-chip { font-size: 10px; font-weight: 500; color: white; padding: 2px 8px; border-radius: 9999px; }
.hop-chip--anchor { color: #1e293b; background: white; border: 3px double #1e293b; }
.hop-chip--unranked { color: #64748b; background: white; border: 1px dashed #94a3b8; }
</style>
