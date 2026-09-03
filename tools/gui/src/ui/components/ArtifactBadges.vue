<script setup lang="ts">
/**
 * The two badges every artifact row carries, as one element.
 *
 * They answer adjacent questions and are always rendered together: `TierBadge` says which
 * repository the artifact belongs to, `ProposedBadge` says whether what is shown matches it. Five
 * surfaces render the pair — the entity, document and diagram lists, search hits and the entity
 * detail header — and the second badge arriving made the cluster worth naming rather than repeating.
 *
 * `suppressTier` is for a view already scoped to one tier: an enterprise-only entity list would
 * otherwise badge every row with the tier the reader just selected.
 */
import type { BaselineStanding } from '../../domain/schemas/baselineStanding'
import { tierFromIsGlobal } from './TierBadge.helpers'
import TierBadge from './TierBadge.vue'
import ProposedBadge from './ProposedBadge.vue'

const props = defineProps<{
  isGlobal: boolean
  standing: BaselineStanding
  suppressTier?: boolean
}>()
</script>

<template>
  <TierBadge
    v-if="props.isGlobal && !props.suppressTier"
    class="row-badge"
    :tier="tierFromIsGlobal(props.isGlobal)"
  />
  <ProposedBadge
    class="row-badge"
    :standing="props.standing"
  />
</template>

<style scoped>
.row-badge { margin-left: 6px; }
</style>
