<script setup lang="ts">
/**
 * Add / remove / reorder list editor for an `array`-typed attribute — each element typed by
 * the array's item schema through the same `TypedPropertyInput` the other kinds use, rather
 * than a raw JSON textarea. Emits the stored JSON-array string, so the host form is unchanged.
 */
import { computed } from 'vue'
import type { EntityAttributeDescriptor, EntityAttributeItemDescriptor } from '../../domain'
import { addItem, moveItem, parseArrayValue, removeItem, serializeArrayValue } from '../lib/arrayPropertyValue'
import TypedPropertyInput from './TypedPropertyInput.vue'

const props = defineProps<{
  modelValue: string
  descriptor: EntityAttributeDescriptor
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const itemDescriptor = computed((): EntityAttributeItemDescriptor => props.descriptor.items ?? { type: 'string' })
const items = computed(() => parseArrayValue(props.modelValue))

const commit = (next: string[]): void => emit('update:modelValue', serializeArrayValue(next, itemDescriptor.value))
const setItem = (index: number, value: string): void => commit(items.value.map((v, i) => (i === index ? value : v)))
</script>

<template>
  <div class="array-input">
    <div
      v-for="(item, i) in items"
      :key="i"
      class="array-row"
    >
      <TypedPropertyInput
        :model-value="item"
        :descriptor="itemDescriptor"
        @update:model-value="setItem(i, $event)"
      />
      <div class="array-controls">
        <button
          type="button"
          class="array-btn"
          :disabled="i === 0"
          title="Move up"
          @click="commit(moveItem(items, i, -1))"
        >
          ↑
        </button>
        <button
          type="button"
          class="array-btn"
          :disabled="i === items.length - 1"
          title="Move down"
          @click="commit(moveItem(items, i, 1))"
        >
          ↓
        </button>
        <button
          type="button"
          class="array-btn array-btn--remove"
          title="Remove"
          @click="commit(removeItem(items, i))"
        >
          ×
        </button>
      </div>
    </div>
    <button
      type="button"
      class="array-add"
      @click="commit(addItem(items))"
    >
      + Add item
    </button>
  </div>
</template>

<style scoped>
.array-input { display: flex; flex-direction: column; gap: 6px; flex: 2; min-width: 0; }
.array-row { display: flex; gap: 6px; align-items: flex-start; }
.array-controls { display: flex; gap: 2px; }
.array-btn {
  width: 22px; height: 30px; border: 1px solid #d1d5db; border-radius: 4px; background: white;
  cursor: pointer; font-size: 12px; color: #374151; line-height: 1;
}
.array-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.array-btn--remove { border-color: #fecaca; color: #dc2626; }
.array-add {
  align-self: flex-start; font-size: 12px; color: #2563eb; background: none;
  border: none; cursor: pointer; padding: 2px 0;
}
.array-add:hover { text-decoration: underline; }
</style>
