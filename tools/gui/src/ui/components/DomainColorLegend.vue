<script setup lang="ts">
import { computed } from 'vue'
import { DOMAIN_COLORS } from '../views/GraphExploreView.helpers'

/** Node-color legend for the exploration surface's default coloring: one chip per
 * ArchiMate domain PRESENT in the current graph — the color coding must never be
 * something the reader has to already know. */
const props = defineProps<{
  domains: readonly (string | undefined)[]
}>()

const entries = computed(() => {
  const present = new Set(props.domains.filter((domain): domain is string => domain !== undefined))
  return Object.entries(DOMAIN_COLORS).filter(([domain]) => present.has(domain))
})
</script>

<template>
  <div
    v-if="entries.length > 1"
    class="domain-legend"
  >
    <span
      v-for="[domain, color] in entries"
      :key="domain"
      class="domain-chip"
    >
      <span
        class="domain-swatch"
        :style="{ background: color }"
      />
      {{ domain }}
    </span>
  </div>
</template>

<style scoped>
.domain-legend {
  display: flex; align-items: center; flex-wrap: wrap; gap: 10px;
  padding: 4px 16px; background: white; border-bottom: 1px solid #e5e7eb;
  font-size: 11px; color: #374151;
}
.domain-chip { display: inline-flex; align-items: center; gap: 4px; }
.domain-swatch { width: 10px; height: 10px; border-radius: 3px; display: inline-block; border: 1px solid rgba(0,0,0,.15); }
</style>
