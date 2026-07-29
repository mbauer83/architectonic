<script setup lang="ts">
import type { CriteriaCatalog } from '../../domain'
import type { GroupKind, GroupNode } from '../../domain/viewpointCriteria'
import { mkGroup } from '../../domain/viewpointCriteria'
import CriteriaTreeBuilder from './CriteriaTreeBuilder.vue'

withDefaults(defineProps<{
  modelValue: GroupNode | null
  groupKind: GroupKind
  catalog: CriteriaCatalog
  depth: number
  bindingNames?: readonly string[]
  parameterNames?: readonly string[]
  /** Field label shown in the panel header, e.g. `connection_criteria`. */
  fieldLabel: string
  /** "any connection" / "any entity" — what a null value means. */
  unrestrictedLabel: string
}>(), { bindingNames: () => [], parameterNames: () => [] })
const emit = defineEmits<{ 'update:modelValue': [value: GroupNode | null] }>()
</script>

<template>
  <div class="builder">
    <div class="builder-header">
      <span class="builder-title">{{ fieldLabel }}</span>
      <button
        v-if="modelValue !== null"
        type="button"
        class="clear-btn"
        @click="emit('update:modelValue', null)"
      >
        ✕ clear ({{ unrestrictedLabel }})
      </button>
    </div>

    <p
      v-if="modelValue === null"
      class="placeholder"
    >
      {{ unrestrictedLabel }}.
      <button
        type="button"
        class="add-btn"
        @click="emit('update:modelValue', mkGroup(groupKind))"
      >
        + Narrow with criteria
      </button>
    </p>
    <CriteriaTreeBuilder
      v-else
      :model-value="modelValue"
      :group-kind="groupKind"
      :catalog="catalog"
      :depth="depth"
      :binding-names="bindingNames"
      :parameter-names="parameterNames"
      is-root
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>
</template>

<style scoped>
.builder { border: 1px dashed #d1d5db; border-radius: 10px; padding: 12px; background: #f9fafb; margin: 8px 0; }
.builder-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.builder-title { font-size: 11px; font-weight: 700; color: #9ca3af; text-transform: uppercase; letter-spacing: .05em; }
.placeholder { font-size: 12.5px; color: #6b7280; margin: 4px 0; }
.clear-btn, .add-btn {
  appearance: none; border: 1px dashed #d1d5db; background: #fff; color: #6b7280;
  border-radius: 7px; padding: 4px 9px; font-size: 11.5px; font-weight: 600; cursor: pointer;
}
.clear-btn:hover, .add-btn:hover { border-color: #6366f1; color: #4338ca; }
</style>
