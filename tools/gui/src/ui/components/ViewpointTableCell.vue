<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { EntityItemSummary } from '../../domain'
import { isColumnSourceResolvable, resolveSummaryColumnValue } from '../views/EntitiesView.helpers'

/** One authored-column table cell: server-resolved value (name cells link to the entity
 * page — every listed entity is a link), a status token badge for `status` columns, an
 * explicit em dash for a missing value, and a marked "not available" state when the
 * source resolves nowhere. */
const props = defineProps<{
  entity: EntityItemSummary
  source: string
}>()

const resolvable = computed(() => isColumnSourceResolvable(props.source, props.entity))
const value = computed(() => resolveSummaryColumnValue(props.entity, props.source))
const isStatusBadge = computed(() => props.source === 'status' && value.value !== null)
const isEntityLink = computed(() => props.source === 'name' && value.value !== null)
</script>

<template>
  <span
    v-if="!resolvable"
    class="vp-col-unavailable"
    title="source not available in results"
  >—</span>
  <RouterLink
    v-else-if="isEntityLink"
    :to="{ path: '/entity', query: { id: entity.id } }"
    class="cell-link"
  >
    {{ value }}
  </RouterLink>
  <span
    v-else-if="isStatusBadge"
    class="status-badge"
    :class="`status--${value}`"
  >{{ value }}</span>
  <template v-else>
    {{ value ?? '—' }}
  </template>
</template>

<style scoped>
.vp-col-unavailable { color: #9ca3af; }
.cell-link { color: #2563eb; text-decoration: none; }
.cell-link:hover { text-decoration: underline; }
</style>
