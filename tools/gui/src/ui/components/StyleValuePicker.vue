<script setup lang="ts">
/**
 * Compact inline picker for one style value string: the five semantic-token swatches,
 * optionally the four named heat-* scale-endpoint swatches, and a "custom" swatch backed
 * by a native color input for an explicit #rrggbb value. Selection is derived purely from
 * the modelValue — a hex value lights up the custom swatch and preloads the color input.
 * Every swatch carries a visible text label — color alone doesn't communicate the token's
 * meaning (positive/critical/…), and unlabeled swatches force guess-and-hover.
 */
import { computed } from 'vue'
import { customColorFor, isCustomSelection, pickerSwatches } from './StyleValuePicker.helpers'

const props = withDefaults(defineProps<{
  modelValue: string | null
  /** Adds the heat-near/heat-far/heat-low/heat-high endpoint swatches. */
  allowScaleEndpoints?: boolean
  /** Adds a leading "(none)" swatch that emits '' — for optional values like defaults. */
  clearable?: boolean
}>(), { allowScaleEndpoints: false, clearable: false })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const swatches = computed(() => pickerSwatches(props.allowScaleEndpoints))
const isCustom = computed(() => isCustomSelection(props.modelValue))
const customColor = computed(() => customColorFor(props.modelValue))
const isCleared = computed(() => props.modelValue === null || props.modelValue === '')
</script>

<template>
  <span class="style-value-picker">
    <span
      v-if="clearable"
      class="swatch-item"
    >
      <button
        type="button"
        class="swatch swatch--none"
        :class="{ sel: isCleared }"
        title="(none)"
        :aria-pressed="isCleared"
        @click="emit('update:modelValue', '')"
      >
        ✕
      </button>
      <span class="swatch-label">none</span>
    </span>
    <span
      v-for="swatch in swatches"
      :key="swatch.token"
      class="swatch-item"
    >
      <button
        type="button"
        class="swatch"
        :class="{ sel: modelValue === swatch.token }"
        :style="{ background: swatch.color }"
        :title="swatch.label"
        :aria-pressed="modelValue === swatch.token"
        @click="emit('update:modelValue', swatch.token)"
      />
      <span class="swatch-label">{{ swatch.label }}</span>
    </span>
    <span class="swatch-item">
      <label
        class="swatch swatch--custom"
        :class="{ sel: isCustom }"
        :style="isCustom ? { background: customColor } : null"
        title="Custom color"
      >
        <input
          type="color"
          :value="customColor"
          @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
        >
      </label>
      <span class="swatch-label">custom</span>
    </span>
  </span>
</template>

<style scoped>
.style-value-picker { display: inline-flex; align-items: flex-start; gap: 6px; flex-wrap: wrap; vertical-align: middle; }
.swatch-item { display: inline-flex; flex-direction: column; align-items: center; gap: 1px; }
.swatch {
  appearance: none; width: 18px; height: 18px; border-radius: 50%; padding: 0;
  border: 1px solid rgba(0, 0, 0, .2); cursor: pointer; position: relative;
  display: inline-flex; align-items: center; justify-content: center; box-sizing: border-box;
}
.swatch.sel { outline: 2px solid #111827; outline-offset: 1px; }
.swatch--none { background: #fff; color: #9ca3af; font-size: 10px; line-height: 1; }
.swatch--custom { background: conic-gradient(#ef4444, #f59e0b, #84cc16, #06b6d4, #6366f1, #d946ef, #ef4444); }
.swatch--custom input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; }
.swatch-label { font-size: 8.5px; color: #6b7280; line-height: 1.1; max-width: 44px; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
