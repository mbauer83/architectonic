<script setup lang="ts">
/**
 * Presentational segmented tier control: emits the typed tier selection and
 * never touches the router — URL persistence belongs to the owning view's
 * useTierFacet composable.
 */
import { computed } from 'vue'
import type { AllowedTierSet, TierSelection } from '../lib/tierUrlState'
import { tierFacetOptions } from './TierFacet.helpers'

const props = defineProps<{ modelValue: TierSelection; allowed: AllowedTierSet }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: TierSelection): void }>()

const options = computed(() => tierFacetOptions(props.allowed))
</script>

<template>
  <div
    class="tier-facet"
    role="group"
    aria-label="Repository tier"
  >
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="tier-option"
      :class="{ active: modelValue === option.value }"
      :aria-pressed="modelValue === option.value"
      @click="emit('update:modelValue', option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>

<style scoped>
.tier-facet {
  display: inline-flex;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  overflow: hidden;
}
.tier-option {
  border: none;
  background: #fff;
  color: #374151;
  font-size: 12px;
  font-weight: 600;
  padding: 4px 12px;
  cursor: pointer;
}
.tier-option + .tier-option { border-left: 1px solid #d1d5db; }
.tier-option.active { background: #1f2937; color: #fff; }
.tier-option:hover:not(.active) { background: #f3f4f6; }
</style>
