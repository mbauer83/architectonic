<script setup lang="ts">
/**
 * Says that what is shown carries local changes not yet accepted upstream, and which fields.
 *
 * Renders nothing for the enterprise baseline — the ordinary case, and a badge under every artifact
 * saying "unchanged" is noise that trains a reader to stop looking at the place the answer appears.
 *
 * Sits beside `TierBadge`, which answers a different question: that one says which repository an
 * artifact belongs to, this one says whether what you are reading matches it.
 */
import type { BaselineStanding } from '../../domain/schemas/baselineStanding'
import { proposedAriaLabel, proposedLabel, proposedVariant } from './ProposedBadge.helpers'

const props = defineProps<{ standing: BaselineStanding }>()
</script>

<template>
  <span
    v-if="proposedLabel(props.standing)"
    class="proposed-badge"
    :class="`proposed-${proposedVariant(props.standing)}`"
    role="img"
    :aria-label="proposedAriaLabel(props.standing) ?? undefined"
  >
    {{ proposedLabel(props.standing) }}
  </span>
</template>

<style scoped>
.proposed-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 99px;
  white-space: nowrap;
}
/* Amber for a change awaiting review; red-tinted where the reader has to act, because `stale` and
   `conflicting` mean the change no longer applies cleanly to what it was written against. */
.proposed-pending { background: #fef3c7; color: #92400e; }
.proposed-attention { background: #fee2e2; color: #991b1b; }
</style>
