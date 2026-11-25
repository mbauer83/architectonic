<script setup lang="ts">
/**
 * One label typed in place on the canvas — a box's, a relation's — with its text selected to type over.
 * Enter keeps it, Escape is the popover's to cancel. *before* is drawn ahead of the field and is never in
 * it: a relation's multiplicity, which its label is drawn after (02·5).
 */
import { nextTick, onMounted, ref } from 'vue'

const props = defineProps<{
  title: string
  value: string
  /** The field's accessible name. */
  field: string
  before?: string
  note?: string
  /** Whether an empty label may be kept: a relation's label may be cleared, a box's may not. */
  optional?: boolean
}>()
const emit = defineEmits<{ keep: [text: string]; cancel: [] }>()

const text = ref(props.value)
const input = ref<HTMLInputElement | null>(null)
onMounted(async () => {
  await nextTick()
  input.value?.select()
})
const keep = () => {
  if (props.optional || text.value.trim()) emit('keep', text.value.trim())
}
</script>

<template>
  <form
    class="cp-form"
    @submit.prevent="keep"
  >
    <h3 class="cp-title">
      {{ title }}
    </h3>
    <label class="cp-field"><span>{{ field }}</span><span class="label-row">
      <span
        v-if="before"
        class="label-before"
      >{{ before }}</span>
      <input
        ref="input"
        v-model="text"
        class="cp-input"
        :aria-label="field"
        :required="!optional"
      >
    </span></label>
    <p
      v-if="note"
      class="cp-note"
    >
      {{ note }}
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
        type="submit"
        class="cp-btn cp-btn--primary"
      >
        Keep <kbd>↵</kbd>
      </button>
    </div>
  </form>
</template>

<style scoped>
.label-row { display: flex; gap: 6px; align-items: center; min-width: 0; }
.label-before { flex: none; color: var(--muted); font-variant-numeric: tabular-nums; }
</style>
