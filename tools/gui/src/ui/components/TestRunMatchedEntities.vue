<script setup lang="ts">
import { computed } from 'vue'
import type { EntityItemSummary } from '../../domain'
import { cappedMatches, derivedMatchTag as derivedTag, hiddenMatchCount } from './TestRunMatchedEntities.helpers'

/** Collapsible matched-entity list for a Test run: names + types (display-capped), with
 * a provenance tag on every entity whose match rested on derived-relationship evidence —
 * so a count is never the only thing standing between the user and a wrong citation. */
const props = defineProps<{
  entities: readonly EntityItemSummary[]
  totalCount: number
}>()

const shown = computed(() => cappedMatches(props.entities))
const hiddenCount = computed(() => hiddenMatchCount(props.entities, props.totalCount))
</script>

<template>
  <details
    v-if="entities.length > 0"
    class="matched-entities"
  >
    <summary>Matched entities ({{ totalCount }})</summary>
    <ul class="matched-list">
      <li
        v-for="entity in shown"
        :key="entity.id"
        class="matched-row"
      >
        <span class="matched-name">{{ entity.name }}</span>
        <span class="matched-type">{{ entity.type }}</span>
        <span
          v-if="derivedTag(entity)"
          class="derived-tag"
        >{{ derivedTag(entity) }}</span>
      </li>
    </ul>
    <div
      v-if="hiddenCount > 0"
      class="matched-more"
    >
      … and {{ hiddenCount }} more (run the viewpoint to see all)
    </div>
  </details>
</template>

<style scoped>
.matched-entities { margin-top: 6px; font-size: 12.5px; }
.matched-entities > summary { cursor: pointer; color: #374151; font-weight: 600; }
.matched-list { list-style: none; margin: 4px 0 0; padding: 0; max-height: 300px; overflow-y: auto; }
.matched-row { display: flex; align-items: baseline; gap: 8px; padding: 1px 0; }
.matched-name { color: #111827; }
.matched-type { color: #6b7280; font-size: 11.5px; }
.derived-tag {
  font-size: 10.5px; color: #7c3aed; background: #f3e8ff;
  padding: 0 6px; border-radius: 9999px; white-space: nowrap;
}
.matched-more { color: #6b7280; margin-top: 2px; }
</style>
