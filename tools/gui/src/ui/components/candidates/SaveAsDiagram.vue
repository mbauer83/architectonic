<script setup lang="ts">
/**
 * *Save as diagram* for a candidate drawn on a view generated from its scope (a search, a viewpoint no
 * stored diagram applies): the view stored as a diagram through the server's one operation for it
 * (`saveCandidateDiagram`), which then draws the candidate on it. A candidate is sketched on a stored
 * diagram's canvas, so this is also what *Sketch on the canvas* offers first where there is none.
 *
 * Saving writes a diagram to the model, and says so: it draws the model's elements as they are, and
 * nothing the candidate changes is written by it.
 */
import { inject, ref } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../../keys'
import { formatEffectError } from '../../lib/errors'

const props = withDefaults(defineProps<{
  candidateId: string
  /** The candidate's name, the diagram's name until the author changes it. */
  name: string
  /** Why the offer is shown: to sketch, or to keep the view. */
  reason?: 'sketch' | 'keep'
}>(), { reason: 'keep' })
const emit = defineEmits<{ saved: [diagram: string]; cancel: [] }>()
const svc = inject(modelServiceKey)!

const diagramName = ref(props.name)
const busy = ref(false)
const error = ref<string | null>(null)

const save = async () => {
  busy.value = true
  error.value = null
  try {
    const read = await Effect.runPromise(svc.readCandidate(props.candidateId))
    const saved = await Effect.runPromise(
      svc.saveCandidateDiagram(props.candidateId, read.version, diagramName.value.trim() || undefined),
    )
    if (saved.diagram) emit('saved', saved.diagram)
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
    @submit.prevent="save"
  >
    <p class="lead">
      <b v-if="reason === 'sketch'">A candidate is sketched on a stored diagram.</b>
      This one is drawn on a view generated from its scope. Save the view as a diagram to
      {{ reason === 'sketch' ? 'sketch on it' : 'keep it' }}: the diagram draws the model's elements as they are
      now and is written to the model when you save it. Nothing this candidate changes is written before it is
      applied.
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
