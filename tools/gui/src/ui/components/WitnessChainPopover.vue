<script setup lang="ts">
/** Resolves and renders one derived relationship's witness chain: the ordered real
 * connections that compose it, as prose with every entity name a clickable sidebar link
 * (via `RouterLink`) — never a synthesized diagram, since the chain itself is never
 * persisted. A broken chain (a connection the walk can't resolve) says so plainly rather
 * than rendering a partial chain as if it were complete. */
import { inject, watch } from 'vue'
import { modelServiceKey } from '../keys'
import { useWitnessChain } from '../composables/useWitnessChain'

const props = defineProps<{ sourceEntityId: string; targetEntityId: string; viaConnectionIds: readonly string[] }>()
defineEmits<{ close: [] }>()
const svc = inject(modelServiceKey)!
const { loading, segments, broken, load } = useWitnessChain(svc)

watch(
  () => [props.sourceEntityId, props.targetEntityId, ...props.viaConnectionIds],
  () => load(props.sourceEntityId, props.targetEntityId, props.viaConnectionIds),
  { immediate: true },
)
</script>

<template>
  <div
    class="witness-popover"
    role="dialog"
    aria-label="Witness chain"
  >
    <div
      v-if="loading"
      class="state-msg"
    >
      Loading witness chain…
    </div>
    <template v-else>
      <p class="chain-prose">
        <template
          v-for="(segment, index) in segments"
          :key="index"
        >
          <RouterLink
            v-if="segment.entityId"
            :to="{ path: '/entity', query: { id: segment.entityId } }"
            class="chain-entity"
          >
            {{ segment.text }}
          </RouterLink>
          <span
            v-else
            class="chain-arrow"
          >{{ segment.text }}</span>
        </template>
      </p>
      <p
        v-if="broken"
        class="chain-broken"
      >
        This witness chain no longer fully resolves — part of it may have changed since it was derived.
      </p>
    </template>
    <button
      class="chain-close"
      @click="$emit('close')"
    >
      Close
    </button>
  </div>
</template>

<style scoped>
.witness-popover {
  position: absolute; z-index: 40; background: white; border: 1px solid #d1d5db; border-radius: 8px;
  padding: 12px 14px; box-shadow: 0 8px 24px rgba(0, 0, 0, .15); max-width: 420px; font-size: 12.5px;
}
.state-msg { color: #6b7280; }
.chain-prose { color: #374151; line-height: 1.6; margin: 0 0 8px; }
.chain-entity { color: #2563eb; font-weight: 600; }
.chain-arrow { color: #6b7280; }
.chain-broken { color: #92400e; background: #fef3c7; padding: 6px 8px; border-radius: 6px; margin: 0 0 8px; }
.chain-close { padding: 4px 10px; border-radius: 6px; border: 1px solid #d1d5db; background: white; font-size: 12px; cursor: pointer; }
</style>
