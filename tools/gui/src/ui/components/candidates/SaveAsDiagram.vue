<script setup lang="ts">
/**
 * *Save as diagram* for a candidate drawn on a view generated from its scope: the view stored as a diagram
 * through the server's one operation for it (`saveCandidateDiagram`), which then draws the candidate on it. An
 * explicit act of its own — a candidate is sketched on its own picture, which needs no stored diagram.
 *
 * Saving writes a diagram to the model, and says so: it draws the model's elements as they are, and
 * nothing the candidate changes is written by it.
 */
import { inject } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../../keys'
import SaveAsDiagramForm from '../SaveAsDiagramForm.vue'

const props = defineProps<{
  candidateId: string
  /** The candidate's name, the diagram's name until the author changes it. */
  name: string
}>()
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
    This candidate is drawn on a view generated from the model elements it reads over. Saving the view as a
    diagram keeps it: the diagram draws the model's elements as they are now and is written to the model when
    you save it. Nothing this candidate changes is written before it is applied.
  </SaveAsDiagramForm>
</template>
