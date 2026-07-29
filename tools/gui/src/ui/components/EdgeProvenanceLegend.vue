<script setup lang="ts">
import { computed } from 'vue'
import type { ConnectionItemSummary } from '../../domain'
import { DERIVED_EDGE_DASH } from '../views/GraphExploreView.helpers'

/** One legend entry per connection-provenance class actually present in the result —
 * modeled (solid), derived-certain, and derived-potential (their dash densities differ
 * by construction), so a dashed edge can never be misread as a modeled type's own
 * dashed notation without a label in sight. */
const props = defineProps<{
  connections: readonly ConnectionItemSummary[]
}>()

interface Entry {
  readonly label: string
  readonly dash: string | undefined
}

const entries = computed((): readonly Entry[] => {
  const present: Entry[] = []
  if (props.connections.some((c) => c.certainty == null)) present.push({ label: 'modeled', dash: undefined })
  if (props.connections.some((c) => c.certainty === 'certain')) {
    present.push({ label: 'derived (certain)', dash: DERIVED_EDGE_DASH.certain })
  }
  if (props.connections.some((c) => c.certainty === 'potential')) {
    present.push({ label: 'derived (potential)', dash: DERIVED_EDGE_DASH.potential })
  }
  return present
})
</script>

<template>
  <div
    v-if="entries.length > 1"
    class="edge-legend"
  >
    <span
      v-for="entry in entries"
      :key="entry.label"
      class="edge-legend-entry"
    >
      <svg
        width="28"
        height="8"
        aria-hidden="true"
      >
        <line
          x1="1"
          y1="4"
          x2="27"
          y2="4"
          stroke="#6b7280"
          stroke-width="1.5"
          :stroke-dasharray="entry.dash"
        />
      </svg>
      {{ entry.label }}
    </span>
  </div>
</template>

<style scoped>
.edge-legend {
  display: flex; align-items: center; flex-wrap: wrap; gap: 10px;
  padding: 4px 16px; background: white; border-bottom: 1px solid #e5e7eb;
  font-size: 11px; color: #374151;
}
.edge-legend-entry { display: inline-flex; align-items: center; gap: 4px; }
</style>
