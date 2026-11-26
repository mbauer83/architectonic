<script setup lang="ts">
/**
 * Renaming an element on the canvas (sketch 01·10): its name, selected to type over, and how far the
 * rename reaches — the other diagrams that draw the element are renamed too. Kept with the session's
 * other changes; nothing is written until Save.
 */
import { computed, inject, nextTick, onMounted, ref } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'

const props = defineProps<{
  element: { readonly id: string; readonly name: string }
  /** The diagram being edited, which does not count among the others that draw it. */
  diagramId: string
  /** Created in this session: no other diagram can draw it yet. */
  drafted: boolean
}>()
const emit = defineEmits<{ apply: [command: CanvasCommand]; cancel: []; failed: [message: string] }>()
const svc = inject(modelServiceKey)!

const name = ref(props.element.name)
const usages = ref<number | null>(props.drafted ? 0 : null)
const field = ref<HTMLInputElement | null>(null)
/** How far the rename reaches, in words that agree with the count. */
const reach = computed(() => {
  const count = usages.value ?? 0
  if (count === 0) return 'No other diagram draws it'
  return `Also renamed on ${count} other diagram${count === 1 ? '' : 's'}`
})

onMounted(async () => {
  await nextTick()
  field.value?.select()
  if (props.drafted) return
  try {
    const entity = await Effect.runPromise(svc.getEntity(props.element.id))
    usages.value = entity.referenced_in_diagrams.filter((d) => d.artifact_id !== props.diagramId).length
  } catch (e) {
    emit('failed', String(e))
  }
})
</script>

<template>
  <form
    class="cp-form"
    @submit.prevent="emit('apply', { op: 'model.element.rename', artifact_id: element.id, name: name.trim() })"
  >
    <h3 class="cp-title">
      Rename {{ element.name }}
    </h3>
    <label class="cp-field"><span>Name</span><input
      ref="field"
      v-model="name"
      class="cp-input"
      required
    ></label>
    <p
      v-if="usages !== null"
      class="cp-note"
    >
      {{ reach }}
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
        Keep rename <kbd>↵</kbd>
      </button>
    </div>
  </form>
</template>
