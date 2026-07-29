<script setup lang="ts">
/**
 * Uniform repository-tier row badge: one semantic, one accessibility label,
 * visual language shared with the viewpoint catalog's tier tag.
 */
import type { Tier } from '../lib/tierUrlState'
import { TIER_LABELS, tierBadgeAriaLabel } from './TierBadge.helpers'

defineProps<{ tier: Tier }>()
</script>

<template>
  <span
    class="tier-badge"
    :class="`tier-${tier}`"
    role="img"
    :aria-label="tierBadgeAriaLabel(tier)"
  >
    {{ TIER_LABELS[tier] }}
  </span>
</template>

<style scoped>
.tier-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 99px;
  white-space: nowrap;
}
.tier-engagement { background: #dcfce7; color: #166534; }
.tier-enterprise { background: #dbeafe; color: #1e40af; }
.tier-module { background: #f3f4f6; color: #6b7280; }
</style>
