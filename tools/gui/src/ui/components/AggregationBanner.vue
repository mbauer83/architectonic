<script setup lang="ts">
/** Banner over an aggregated exploration: what the super-node view is (dimension, group
 * count, budget), the click-to-expand affordance, the truncated-expansion honesty note,
 * and — when aggregation cannot reduce the view — the filter/representation/anchor
 * choice prompt. */
import type { AggregationSummary } from '../../domain'

defineProps<{
  aggregation: AggregationSummary
  hint: string | null
  totalEntityCount: number
  missingMemberCount: number
}>()
</script>

<template>
  <div class="aggregation-banner">
    <template v-if="hint">
      {{ hint }}
    </template>
    <template v-else>
      Opened as {{ aggregation.nodes.length }} {{ aggregation.dimension }} groups
      ({{ totalEntityCount }} entities — over this view's legibility budget of
      {{ aggregation.legibility_budget }}). Click a group to expand it.
      <span v-if="missingMemberCount > 0">
        {{ missingMemberCount }} member(s) of expanded groups are beyond the returned page and not shown.
      </span>
    </template>
  </div>
</template>

<style scoped>
.aggregation-banner {
  font-size: 12px; color: #1e40af; background: #eff6ff; border: 1px solid #bfdbfe;
  border-radius: 7px; padding: 7px 11px; margin: 6px 0;
}
</style>
