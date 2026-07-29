<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import type { ViewpointDefinitionEnvelope, ViewpointExecutionResult } from '../../domain'
import { verifiedReferenceMismatch, type VerifiedPins } from '../lib/viewpointUrlState'
import ExecutionLinkActions from './ExecutionLinkActions.vue'

/** The addressable-execution strip: the copy-link affordances (live vs verified) and the
 * moved-state notice a verified reference shows when the model generation or the
 * definition content has changed since it was captured. */
const props = defineProps<{
  envelope: ViewpointDefinitionEnvelope | null
  result: ViewpointExecutionResult | null
}>()

const route = useRoute()

const pins = computed((): VerifiedPins | null => {
  if (!props.envelope || !props.result || props.envelope.definition_digest === undefined) return null
  return {
    version: props.envelope.version,
    definitionDigest: props.envelope.definition_digest,
    generation: props.result.index_generation,
  }
})

const mismatch = computed(() =>
  verifiedReferenceMismatch(route.query, props.result, props.envelope?.definition_digest ?? null),
)
</script>

<template>
  <div
    v-if="mismatch"
    class="reference-mismatch"
  >
    {{ mismatch }}
  </div>
  <div
    v-if="result"
    class="link-actions-bar"
  >
    <ExecutionLinkActions :pins="pins" />
  </div>
</template>

<style scoped>
.reference-mismatch {
  padding: 4px 16px; background: #fef3c7; border-bottom: 1px solid #fde68a;
  color: #92400e; font-size: 12px;
}
.link-actions-bar { padding: 4px 16px; background: white; border-bottom: 1px solid #e5e7eb; }
</style>
