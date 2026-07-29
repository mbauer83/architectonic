<script setup lang="ts">
/**
 * The connection / direction / endpoint-type trio shared by a branch edge and a shortcut edge
 * (both are edges with those three fields — DRY, so the two never drift). Presentational:
 * emits each field change; the parent owns the edge object and the mutation helper.
 */
import type { CriteriaCatalog } from '../../domain'
import type { EdgeDirection } from '../../domain/viewpointTracePattern'

defineProps<{
  connection: string
  direction: EdgeDirection
  endpointType: string
  catalog: CriteriaCatalog
}>()
const emit = defineEmits<{
  connection: [value: string]
  direction: [value: EdgeDirection]
  endpointType: [value: string]
}>()
const value = (e: Event) => (e.target as HTMLSelectElement).value
</script>

<template>
  <select
    class="inp"
    :value="connection"
    @change="emit('connection', value($event))"
  >
    <option value="">
      — connection —
    </option>
    <option
      v-for="c in catalog.connection_types"
      :key="c"
      :value="c"
    >
      {{ c }}
    </option>
  </select>
  <select
    class="inp"
    :value="direction"
    @change="emit('direction', value($event) as EdgeDirection)"
  >
    <option value="incoming">
      incoming
    </option>
    <option value="outgoing">
      outgoing
    </option>
  </select>
  <select
    class="inp"
    :value="endpointType"
    @change="emit('endpointType', value($event))"
  >
    <option value="">
      — endpoint type —
    </option>
    <option
      v-for="t in catalog.entity_types"
      :key="t"
      :value="t"
    >
      {{ t }}
    </option>
  </select>
</template>

<style scoped>
.inp { font-size: 12.5px; padding: 4px 8px; border-radius: 6px; border: 1px solid #d1d5db; background: #fff; }
</style>
