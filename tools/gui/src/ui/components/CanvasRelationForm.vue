<script setup lang="ts">
/**
 * A relation drawn, or edited, on the canvas (sketch 03·8): its type from what the ontology permits
 * between the two ends, its cardinalities and description in the model, and the label this diagram
 * draws on the line. Kept with the session's other changes; nothing is written until Save.
 */
import { nextTick, onMounted, ref } from 'vue'

defineProps<{
  /** "Source → Target", in the elements' names. */
  title: string
  options: readonly string[]
  /** Whether the relation is in the model already, so keeping it edits rather than creates it. */
  editing: boolean
}>()
const emit = defineEmits<{ keep: []; cancel: [] }>()
const kind = defineModel<string>('kind', { required: true })
const srcCount = defineModel<string>('srcCount', { required: true })
const tgtCount = defineModel<string>('tgtCount', { required: true })
const description = defineModel<string>('description', { required: true })
const label = defineModel<string>('label', { required: true })

const first = ref<HTMLSelectElement | null>(null)
onMounted(() => void nextTick(() => first.value?.focus()))
</script>

<template>
  <form
    class="cp-form"
    @submit.prevent="emit('keep')"
  >
    <h3 class="cp-title">
      {{ title }}
    </h3>
    <label class="cp-field">
      <span>Relationship</span>
      <select
        ref="first"
        v-model="kind"
        class="cp-input"
      >
        <option
          v-for="k in options"
          :key="k"
        >{{ k }}</option>
      </select>
    </label>
    <p class="cp-section">
      In the model
    </p>
    <label class="cp-field">
      <span>Source cardinality</span>
      <input
        v-model="srcCount"
        class="cp-input"
        placeholder="e.g. 1"
      >
    </label>
    <label class="cp-field">
      <span>Target cardinality</span>
      <input
        v-model="tgtCount"
        class="cp-input"
        placeholder="e.g. 0..*"
      >
    </label>
    <label class="cp-field">
      <span>Description</span>
      <input
        v-model="description"
        class="cp-input"
      >
    </label>
    <p class="cp-section">
      On this diagram
    </p>
    <label class="cp-field">
      <span>Diagram label</span>
      <input
        v-model="label"
        class="cp-input"
        placeholder="Optional, shown on the line"
      >
    </label>
    <p class="cp-note">
      {{ editing ? 'The change' : 'A created relation' }} is written to the model when you Save.
      <kbd>Esc</kbd> draws nothing.
    </p>
    <div class="cp-row-end">
      <button
        type="button"
        class="cp-btn"
        @click="emit('cancel')"
      >
        Cancel
      </button>
      <button
        :disabled="!kind"
        type="submit"
        class="cp-btn cp-btn--primary"
      >
        Keep relationship
      </button>
    </div>
  </form>
</template>
