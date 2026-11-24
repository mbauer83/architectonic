<script setup lang="ts">
/**
 * Multi-select over a fixed, enumerable value set, rendered as toggleable chips — the
 * value input for an `in`/`not_in` condition whose attribute has known choices (a schema
 * `enum`, or a reserved facet like `status`/`domain`). Replaces the comma-separated
 * free-text list so the user picks only from the valid set. Pure display + toggle; the
 * selected list is the model.
 */
const props = defineProps<{
  modelValue: readonly string[]
  choices: readonly string[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()

const toggle = (choice: string) => {
  const next = props.modelValue.includes(choice)
    ? props.modelValue.filter((v) => v !== choice)
    : [...props.modelValue, choice]
  emit('update:modelValue', next)
}
</script>

<template>
  <div
    class="chip-row"
    role="group"
    aria-label="value"
  >
    <button
      v-for="choice in choices"
      :key="choice"
      type="button"
      class="chip"
      :class="{ on: modelValue.includes(choice) }"
      :aria-pressed="modelValue.includes(choice)"
      @click="toggle(choice)"
    >
      {{ choice }}
    </button>
  </div>
</template>

<style scoped>
.chip-row { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.chip {
  appearance: none; border: 1px solid var(--border-strong); background: var(--surface); border-radius: 999px;
  padding: 3px 10px; font-size: 12px; color: var(--text-2); cursor: pointer;
}
.chip:hover { border-color: var(--indigo); color: var(--indigo-text); }
.chip:focus-visible { outline: 2px solid var(--indigo); outline-offset: 2px; }
.chip.on { background: var(--indigo); border-color: var(--indigo); color: var(--on-accent); }
</style>
