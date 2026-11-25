<script setup lang="ts">
/**
 * A relation drawn, or edited, on the canvas (sketch 03·8, 01·10). Drawn: one choice, each a sentence read
 * source to target, under two headings — **In the model: draw it**, the relations the model holds between
 * the two that this diagram does not draw (diagram content only), and **Not in the model: create it**, the
 * types the ontology permits between them that the model does not hold (a model change). Then the label
 * this diagram draws on the line, and, folded, the new relation's cardinalities and description. Edited:
 * its type is shown, not changed. Kept with the session's other changes; nothing is written until Save.
 */
import { nextTick, onMounted, ref, watch } from 'vue'
import { connectionTypeLabel } from '../../domain/connectionTypeLabel'

const props = defineProps<{
  /** The two ends' names. */
  source: string
  target: string
  /** The types that may be created between them. */
  options: readonly string[]
  /** The relations the model holds between them that this diagram does not draw. */
  inModel: readonly { readonly id: string; readonly type: string }[]
  /** Whether the relation is in the model and drawn already, so keeping it edits it. */
  editing: boolean
}>()
const emit = defineEmits<{ keep: []; cancel: [] }>()
const kind = defineModel<string>('kind', { required: true })
/** The relation of the model chosen to be drawn; empty while a type to create is chosen. */
const drawing = defineModel<string>('drawing', { required: true })
const srcCount = defineModel<string>('srcCount', { required: true })
const tgtCount = defineModel<string>('tgtCount', { required: true })
const description = defineModel<string>('description', { required: true })
const label = defineModel<string>('label', { required: true })

const form = ref<HTMLFormElement | null>(null)
/** The choice made, or the first field of a relation being edited, takes the focus. */
const focusChoice = () => void nextTick(() =>
  form.value?.querySelector<HTMLElement>('input[type="radio"]:checked, [data-first]')?.focus())
onMounted(focusChoice)
// The choices arrive after the dialog opens, from the model and the ontology.
watch(() => props.inModel.length + props.options.length, focusChoice)

/** A relationship type as a sentence, read source to target. */
const sentence = (type: string) => `${props.source} — ${connectionTypeLabel(type)} → ${props.target}`
const toDraw = (id: string) => { drawing.value = id; kind.value = '' }
const toCreate = (type: string) => { kind.value = type; drawing.value = '' }
</script>

<template>
  <form
    ref="form"
    class="cp-form"
    @submit.prevent="emit('keep')"
  >
    <h3 class="cp-title">
      {{ source }} → {{ target }}
    </h3>
    <template v-if="editing">
      <p class="cp-section">
        Type
      </p>
      <p
        class="cp-note"
        tabindex="-1"
        data-first
      >
        <b>{{ connectionTypeLabel(kind) }}</b> — {{ sentence(kind) }}.
        To change the type, remove the relation and draw another.
      </p>
    </template>
    <div
      v-else
      class="rel-choices"
      role="radiogroup"
      aria-label="Relationship"
    >
      <p class="cp-section">
        In the model: draw it
      </p>
      <label
        v-for="one in inModel"
        :key="one.id"
        class="rel-choice"
      >
        <input
          type="radio"
          name="relation"
          :checked="drawing === one.id"
          @change="toDraw(one.id)"
        >
        <span><b>{{ connectionTypeLabel(one.type) }}</b><small>{{ sentence(one.type) }}</small></span>
      </label>
      <p
        v-if="!inModel.length"
        class="cp-note"
      >
        The model has no relation from the first to the second.
      </p>
      <p class="cp-section">
        Not in the model: create it
      </p>
      <label
        v-for="type in options"
        :key="type"
        class="rel-choice"
      >
        <input
          type="radio"
          name="relation"
          :checked="!drawing && kind === type"
          @change="toCreate(type)"
        >
        <span><b>{{ connectionTypeLabel(type) }}</b><small>{{ sentence(type) }}</small></span>
      </label>
      <p
        v-if="!options.length"
        class="cp-note"
      >
        The ontology permits no further relation between these two types.
      </p>
    </div>
    <label class="cp-field">
      <span>Label</span>
      <input
        v-model="label"
        class="cp-input"
        placeholder="Optional, shown on the line"
      >
    </label>
    <details
      v-if="!drawing"
      class="rel-more"
      :open="editing"
    >
      <summary>Description and attributes <small>optional · in the model</small></summary>
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
    </details>
    <p class="cp-note">
      {{ drawing ? 'Drawn on this diagram only; the model is not changed.'
        : `${editing ? 'The change' : 'A created relation'} is written to the model when you Save.` }}
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
        :disabled="!kind && !drawing"
        type="submit"
        class="cp-btn cp-btn--primary"
      >
        {{ drawing ? 'Draw relationship' : 'Keep relationship' }}
      </button>
    </div>
  </form>
</template>

<style scoped>
.rel-choices { display: grid; gap: 2px; max-height: 240px; overflow-y: auto; overscroll-behavior: contain; }
.rel-choice {
  display: flex; gap: 8px; align-items: flex-start; padding: 4px 6px; border-radius: 5px; cursor: pointer;
  font-size: 12px;
}
.rel-choice:hover, .rel-choice:focus-within { background: var(--soft); }
.rel-choice span { display: grid; gap: 1px; }
.rel-choice small { color: var(--muted); font-size: 11px; }
.rel-more summary { cursor: pointer; font-size: 12px; color: var(--text-2); margin: 4px 0; }
.rel-more summary small { color: var(--faint); }
.rel-more .cp-field { margin-top: 4px; }
</style>
