<script setup lang="ts">
/**
 * Give one instance the label it carries on this diagram.
 *
 * Opens prefilled with what the box says now, so the common edit — shortening a long name — is a
 * matter of deleting words rather than retyping them. "Use the element's name" withdraws the
 * diagram's statement rather than writing the name down as a label: a label that merely repeats the
 * name would go stale the moment the element is renamed.
 */
import { ref, useTemplateRef, onMounted } from 'vue'

const props = defineProps<{
  /** What the box carries right now. */
  current: string
  /** What the element calls itself — the label a withdrawal returns to. */
  elementLabel: string
  /** Whether the diagram states a label for this instance at all. */
  stated: boolean
}>()

const emit = defineEmits<{
  /** `null` withdraws the diagram's statement. */
  apply: [label: string | null]
  cancel: []
}>()

const draft = ref(props.current)
const input = useTemplateRef<HTMLInputElement>('input')
onMounted(() => { input.value?.focus(); input.value?.select() })

const apply = (): void => {
  const trimmed = draft.value.trim()
  emit('apply', trimmed && trimmed !== props.elementLabel ? trimmed : null)
}
</script>

<template>
  <form
    class="dle"
    @submit.prevent="apply"
  >
    <label class="dle__label">
      <span class="dle__caption">Label on this diagram</span>
      <input
        ref="input"
        v-model="draft"
        class="dle__input"
        type="text"
        :placeholder="elementLabel"
        @keydown.esc.prevent="emit('cancel')"
      >
    </label>
    <div class="dle__actions">
      <button
        type="submit"
        class="dle__apply"
      >
        Apply
      </button>
      <button
        v-if="stated"
        type="button"
        class="dle__reset"
        title="Withdraw this diagram's label so the box shows the element's own name again"
        @click="emit('apply', null)"
      >
        Use the element's name
      </button>
      <button
        type="button"
        class="dle__cancel"
        @click="emit('cancel')"
      >
        Cancel
      </button>
    </div>
    <p class="dle__hint">
      Changes what this box says here only. The element keeps its name: {{ elementLabel }}
    </p>
  </form>
</template>

<style scoped>
.dle {
  display: flex; flex-direction: column; gap: 6px; padding: 8px 10px 10px;
  border-top: 1px solid #f3f4f6; background: #faf5ff;
}
.dle__label { display: flex; flex-direction: column; gap: 3px; }
.dle__caption {
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #6d28d9;
}
.dle__input {
  padding: 5px 8px; border: 1px solid #ddd6fe; border-radius: 6px; font-size: 13px; color: #1f2937; background: #fff;
}
.dle__input:focus { outline: 2px solid #c4b5fd; outline-offset: 1px; }
.dle__actions { display: flex; gap: 6px; flex-wrap: wrap; }
.dle__apply, .dle__reset, .dle__cancel {
  padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent;
}
.dle__apply { background: #6d28d9; color: #fff; }
.dle__apply:hover { background: #5b21b6; }
.dle__reset { background: #fff; color: #6d28d9; border-color: #ddd6fe; }
.dle__reset:hover { background: #f5f3ff; }
.dle__cancel { background: none; color: #6b7280; }
.dle__cancel:hover { color: #374151; }
.dle__hint { margin: 0; font-size: 11px; color: #6b7280; }
</style>
