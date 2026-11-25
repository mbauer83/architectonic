<script setup lang="ts">
/**
 * *Save as diagram* for a view the product generated rather than stored — a candidate's scope, a viewpoint's
 * picture: a name, and the save. What saving writes is the caller's to say, in the lead (the default slot),
 * and to do (*save*, which answers the stored diagram's id); a refusal is said here in words.
 */
import { ref } from 'vue'
import { formatEffectError } from '../lib/errors'

const props = defineProps<{
  /** The diagram's name until the author changes it. */
  name: string
  /** Writes the diagram under the name given, answering its id. */
  save: (name: string) => Promise<string>
}>()
const emit = defineEmits<{ saved: [diagram: string]; cancel: [] }>()

const diagramName = ref(props.name)
const busy = ref(false)
const error = ref<string | null>(null)

const submit = async () => {
  busy.value = true
  error.value = null
  try {
    emit('saved', await props.save(diagramName.value.trim()))
  } catch (failure) {
    error.value = formatEffectError(failure)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form
    class="save-diagram card"
    aria-label="Save as diagram"
    data-testid="save-as-diagram"
    @submit.prevent="submit"
  >
    <p class="lead">
      <slot />
    </p>
    <label>Diagram name <input
      v-model="diagramName"
      required
      data-testid="save-as-diagram-name"
    ></label>
    <button
      type="submit"
      class="btn btn-sm btn-primary"
      data-testid="save-as-diagram-confirm"
      :disabled="busy || !diagramName.trim()"
    >
      Save as diagram
    </button>
    <button
      type="button"
      class="btn btn-sm"
      @click="emit('cancel')"
    >
      Cancel
    </button>
    <p
      v-if="error"
      class="err"
      role="alert"
    >
      {{ error }}
    </p>
  </form>
</template>

<style scoped>
.save-diagram { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 8px 10px; margin: 0 0 8px;
  font-size: 12.5px; }
.lead { flex-basis: 100%; margin: 0; color: var(--text-2); }
.save-diagram input { font: inherit; margin-left: 4px; min-width: 240px; }
.err { flex-basis: 100%; margin: 0; color: var(--danger-strong); }
</style>
