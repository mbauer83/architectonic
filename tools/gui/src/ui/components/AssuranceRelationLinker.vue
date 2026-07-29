<script setup lang="ts">
/**
 * Links one authored assurance node to a node it should point at, using a relation the
 * ontology registers. Shared by every wizard step that declares an outgoing relation, so
 * the affordance behaves identically wherever a chain has to be closed.
 */

interface LinkTarget {
  node_id: string
  name: string
}

defineProps<{
  /** Registered connection type the emitted link will be created with. */
  connType: string
  /** Human-readable name of the target kind, used in the prompt option. */
  targetLabel: string
  /** True once the source node already holds this relation. */
  linked: boolean
  targets: LinkTarget[]
  disabled?: boolean
}>()

const emit = defineEmits<{ link: [targetId: string] }>()

function onSelect(event: Event): void {
  const { value } = event.target as HTMLSelectElement
  if (value) emit('link', value)
}
</script>

<template>
  <span class="relation">
    <span
      v-if="linked"
      class="relation-set"
    >{{ connType }} ✓</span>
    <select
      v-else
      class="relation-select"
      :disabled="disabled"
      :aria-label="`Link ${connType} ${targetLabel}`"
      @change="onSelect"
    >
      <option value="">
        {{ connType }} {{ targetLabel }}…
      </option>
      <option
        v-for="t in targets"
        :key="t.node_id"
        :value="t.node_id"
      >
        {{ t.name }}
      </option>
    </select>
  </span>
</template>

<style scoped>
.relation { display: inline-flex; align-items: center; gap: 6px; }
.relation-select { font-size: 12px; padding: 4px 8px; border: 1px solid #cbd5e1; border-radius: 5px; }
.relation-set { font-size: 12px; color: #15803d; font-weight: 600; }
</style>
