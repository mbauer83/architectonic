<script setup lang="ts">
/**
 * Scale-mode fields of one style rule: the driving attribute (a combobox over numeric
 * schema attributes plus the query's declared `derived.<name>` entries, with an inline
 * warning for references outside that set), optional bounds (empty = data-driven), the
 * two gradient endpoints, and a live gradient preview. Standard
 * modelValue/update:modelValue binding on the whole rule node.
 */
import { computed } from 'vue'
import { DEFAULT_SCALE_TOKENS, parseScaleBound } from '../../domain/viewpointPresentation'
import type { StyleRuleNode } from '../../domain/viewpointPresentation'
import { tokenColor } from '../lib/viewpointStyleTokens'
import StyleValuePicker from './StyleValuePicker.vue'

const props = defineProps<{
  modelValue: StyleRuleNode
  /** Every reference the rule may legally use: numeric schema attributes plus the
   * query's declared `derived.<name>` entries. */
  attributeOptions: readonly string[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: StyleRuleNode] }>()

const emitUpdate = (patch: Partial<StyleRuleNode>) => emit('update:modelValue', { ...props.modelValue, ...patch })

const unknownReference = computed(() => {
  const value = props.modelValue.scaleAttribute
  return value !== null && value.length > 0 && !props.attributeOptions.includes(value)
})

const endpoints = computed((): readonly [string, string] => props.modelValue.scaleTokens ?? DEFAULT_SCALE_TOKENS)
const setEndpoint = (position: 0 | 1, token: string) => {
  const [near, far] = endpoints.value
  emitUpdate({ scaleTokens: position === 0 ? [token, far] : [near, token] })
}
const gradient = computed(() => {
  const [near, far] = endpoints.value
  return `linear-gradient(to right, ${tokenColor(near)}, ${tokenColor(far)})`
})
</script>

<template>
  <div class="scale-fields">
    <label class="value-line">
      scale_attribute:
      <input
        class="inp scale-attr"
        :class="{ 'scale-attr--unknown': unknownReference }"
        :value="modelValue.scaleAttribute ?? ''"
        :list="`scale-attrs-${modelValue.id}`"
        placeholder="numeric attribute or derived.<name>"
        @input="emitUpdate({ scaleAttribute: ($event.target as HTMLInputElement).value || null })"
      >
      <datalist :id="`scale-attrs-${modelValue.id}`">
        <option
          v-for="attr in attributeOptions"
          :key="attr"
          :value="attr"
        />
      </datalist>
      <span
        v-if="unknownReference"
        class="attr-warning"
      >not a numeric attribute or declared derived name — the rule would style nothing</span>
    </label>
    <label class="value-line">
      bounds:
      <input
        class="inp bound-input"
        placeholder="auto"
        :value="modelValue.scaleMin ?? ''"
        @input="emitUpdate({ scaleMin: parseScaleBound(($event.target as HTMLInputElement).value) })"
      >
      <span>to</span>
      <input
        class="inp bound-input"
        placeholder="auto"
        :value="modelValue.scaleMax ?? ''"
        @input="emitUpdate({ scaleMax: parseScaleBound(($event.target as HTMLInputElement).value) })"
      >
    </label>
    <div class="value-line">
      gradient:
      <StyleValuePicker
        :model-value="endpoints[0]"
        allow-scale-endpoints
        @update:model-value="setEndpoint(0, $event)"
      />
      <span>→</span>
      <StyleValuePicker
        :model-value="endpoints[1]"
        allow-scale-endpoints
        @update:model-value="setEndpoint(1, $event)"
      />
    </div>
    <div
      class="gradient-preview"
      :style="{ background: gradient }"
    />
  </div>
</template>

<style scoped>
.value-line { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: #6b7280; margin-top: 8px; }
.inp { padding: 4px 6px; border-radius: 5px; border: 1px solid #d1d5db; font-size: 12.5px; font-family: inherit; }
.scale-attr { min-width: 220px; }
.scale-attr--unknown { border-color: #dc2626; }
.attr-warning { color: #dc2626; font-size: 11.5px; }
.bound-input { width: 90px; }
.gradient-preview { height: 10px; max-width: 280px; border-radius: 5px; border: 1px solid rgba(0,0,0,.1); margin-top: 6px; }
</style>
