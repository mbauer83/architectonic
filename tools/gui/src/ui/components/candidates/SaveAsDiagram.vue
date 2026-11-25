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
import { inject } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../../keys'
import SaveAsDiagramForm from '../SaveAsDiagramForm.vue'

const props = withDefaults(defineProps<{
  candidateId: string
  /** The candidate's name, the diagram's name until the author changes it. */
  name: string
  /** Why the offer is shown: to sketch, or to keep the view. */
  reason?: 'sketch' | 'keep'
}>(), { reason: 'keep' })
const emit = defineEmits<{ saved: [diagram: string]; cancel: [] }>()
const svc = inject(modelServiceKey)!

const save = async (diagramName: string): Promise<string> => {
  const read = await Effect.runPromise(svc.readCandidate(props.candidateId))
  const saved = await Effect.runPromise(
    svc.saveCandidateDiagram(props.candidateId, read.version, diagramName || undefined),
  )
  if (!saved.diagram) throw new Error('The view was not saved as a diagram.')
  return saved.diagram
}
</script>

<template>
  <SaveAsDiagramForm
    :name="name"
    :save="save"
    operation="changes_save_candidate_diagram"
    @saved="emit('saved', $event)"
    @cancel="emit('cancel')"
  >
    <b v-if="reason === 'sketch'">A candidate is sketched on a stored diagram.</b>
    This one is drawn on a view generated from its scope. Save the view as a diagram to
    {{ reason === 'sketch' ? 'sketch on it' : 'keep it' }}: the diagram draws the model's elements as they are
    now and is written to the model when you save it. Nothing this candidate changes is written before it is
    applied.
  </SaveAsDiagramForm>
</template>
