<script setup lang="ts">
/**
 * *Save as diagram* for a viewpoint's picture, which the product draws on request and never stores: the
 * elements the execution found and the model's relations among them, written as a new diagram of the
 * layered ArchiMate type the picture is drawn as — through the one diagram create every editor uses. A
 * derived relation is the viewpoint's reading, not the model's, and is not written.
 *
 * Once stored, the diagram is the author's: it is opened, arranged and saved like any other, and does not
 * follow the viewpoint when the model changes.
 */
import { inject } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { ViewpointExecutionResult } from '../../domain/schemas/viewpoints'
import { collectVerificationIssues } from '../lib/errors'
import SaveAsDiagramForm from './SaveAsDiagramForm.vue'

/** The diagram type a viewpoint's picture is drawn as, and so the type it is saved as. */
const DRAWN_AS = 'archimate-layered'

const props = defineProps<{ name: string; execution: ViewpointExecutionResult }>()
const emit = defineEmits<{ saved: [diagram: string]; cancel: [] }>()
const svc = inject(modelServiceKey)!

const save = async (name: string): Promise<string> => {
  const written = await Effect.runPromise(svc.createDiagram({
    diagram_type: DRAWN_AS, name,
    entity_ids: props.execution.entities.map((entity) => entity.id),
    connection_ids: props.execution.connections.filter((relation) => relation.certainty == null)
      .map((relation) => relation.id),
    dry_run: false,
  }))
  if (!written.wrote) {
    throw new Error(collectVerificationIssues(written.verification).join(' | ') || 'The diagram was not written.')
  }
  return written.artifact_id
}
</script>

<template>
  <SaveAsDiagramForm
    :name="name"
    :save="save"
    operation="diagrams_create_diagram"
    @saved="emit('saved', $event)"
    @cancel="emit('cancel')"
  >
    This picture is drawn from the model each time the viewpoint is opened, and is not stored. Saved as a
    diagram, its {{ execution.entities.length }} elements and the relations the model holds among them are
    written to the model as a diagram of their own, which can be arranged and edited. It does not follow the
    viewpoint afterwards.
  </SaveAsDiagramForm>
</template>
