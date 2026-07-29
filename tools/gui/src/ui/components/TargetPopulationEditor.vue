<script setup lang="ts">
import { ref } from 'vue'

/** Declares the TARGET population a view is about — the honest-empty header keys off it
 * ("this model contains no X; showing …"). Undeclared means UNKNOWN: execution then
 * shows plain counts and makes no absence claims, so declaring this is what buys the
 * view truthful empty-state messaging in query mode. */
const props = defineProps<{
  modelValue: string[] | null
  entityTypes: readonly string[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string[] | null] }>()

const pending = ref('')

const add = () => {
  const type = pending.value.trim()
  if (!type) return
  const current = props.modelValue ?? []
  if (!current.includes(type)) emit('update:modelValue', [...current, type].sort())
  pending.value = ''
}

const remove = (type: string) => {
  const next = (props.modelValue ?? []).filter((t) => t !== type)
  emit('update:modelValue', next.length > 0 ? next : null)
}
</script>

<template>
  <div class="target-population">
    <h3>Target population</h3>
    <p class="hint">
      The entity types this view is ABOUT. When none of them exist, execution says so
      honestly instead of showing helper noise; leave undeclared and no absence claims
      are ever made.
    </p>
    <div class="chips">
      <span
        v-for="type in modelValue ?? []"
        :key="type"
        class="chip"
      >
        {{ type }}
        <button
          type="button"
          class="chip-remove"
          :aria-label="`Remove ${type}`"
          @click="remove(type)"
        >✕</button>
      </span>
      <span
        v-if="(modelValue ?? []).length === 0"
        class="undeclared"
      >undeclared</span>
    </div>
    <div class="add-row">
      <input
        v-model="pending"
        class="inp"
        list="target-population-types"
        placeholder="entity type…"
        @keydown.enter.prevent="add"
      >
      <datalist id="target-population-types">
        <option
          v-for="type in entityTypes"
          :key="type"
          :value="type"
        />
      </datalist>
      <button
        type="button"
        class="btn"
        @click="add"
      >
        + Add
      </button>
    </div>
  </div>
</template>

<style scoped>
.target-population { margin-top: 14px; }
.hint { font-size: 12px; color: #6b7280; margin: 2px 0 6px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.chip {
  display: inline-flex; align-items: center; gap: 4px; font-size: 12px;
  background: #eef2ff; color: #3730a3; border-radius: 9999px; padding: 2px 8px;
}
.chip-remove { border: none; background: none; cursor: pointer; color: #6366f1; padding: 0; }
.undeclared { font-size: 12px; color: #9ca3af; font-style: italic; }
.add-row { display: flex; gap: 6px; align-items: center; }
.inp { padding: 4px 6px; border-radius: 5px; border: 1px solid #d1d5db; font-size: 12.5px; min-width: 220px; }
.btn { font-size: 12px; padding: 4px 10px; border: 1px solid #d1d5db; border-radius: 5px; background: white; cursor: pointer; }
</style>
