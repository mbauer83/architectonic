<script setup lang="ts">
/** Turns one derived (never separately modeled) relationship into a real connection —
 * "materialize" — by pre-filling the existing `ConnectionAddForm` with the relationship's
 * already-known type/endpoints/description rather than making the user search for them
 * again. Fetches the same ontology-classification/guidance data `ConnectionsPanel` does,
 * scoped to this one source entity's type. */
import { computed, inject, onMounted } from 'vue'
import { modelServiceKey } from '../keys'
import type { AuthoringGuidance, OntologyClassification } from '../../domain'
import type { RepoError } from '../../ports/ModelRepository'
import { useQuery } from '../composables/useQuery'
import ConnectionAddForm from './ConnectionAddForm.vue'

const props = defineProps<{
  sourceEntityId: string
  sourceEntityType: string
  targetEntityId: string
  targetEntityName: string
  targetEntityType: string
  connType: string
  hops: number | null
}>()
const emit = defineEmits<{ added: []; cancel: [] }>()

const svc = inject(modelServiceKey)!
const ontologyQuery = useQuery<OntologyClassification, RepoError>()
const guidanceQuery = useQuery<AuthoringGuidance, RepoError>()

onMounted(() => {
  ontologyQuery.run(svc.getOntologyClassification(props.sourceEntityType))
  guidanceQuery.run(svc.getAuthoringGuidance({ entityTypes: [props.sourceEntityType] }))
})

const symmetricConnTypes = computed((): Set<string> => {
  const ontology = ontologyQuery.data.value
  if (!ontology) return new Set()
  const types = new Set<string>()
  for (const conns of Object.values(ontology.symmetric)) {
    for (const ct of conns) types.add(ct)
  }
  return types
})

const description = `Materialized from a derived relationship (${props.hops ?? '?'} hop${props.hops === 1 ? '' : 's'}).`
</script>

<template>
  <div class="materialize-backdrop">
    <div
      class="materialize-panel"
      role="dialog"
      aria-label="Materialize connection"
    >
      <h2>Materialize this relationship</h2>
      <p class="materialize-hint">
        This derived relationship isn't a real connection yet. Confirm and save it as one.
      </p>
      <ConnectionAddForm
        :entity-id="sourceEntityId"
        :entity-type="sourceEntityType"
        :type-key="targetEntityType"
        direction="outgoing"
        :symmetric-conn-types="symmetricConnTypes"
        :guidance="guidanceQuery.data.value"
        :initial-target="{ id: targetEntityId, name: targetEntityName }"
        :initial-conn-type="connType"
        :initial-description="description"
        @added="emit('added')"
        @cancel="emit('cancel')"
      />
    </div>
  </div>
</template>

<style scoped>
.materialize-backdrop { position: fixed; inset: 0; background: rgba(17, 24, 39, .4); display: flex; align-items: center; justify-content: center; z-index: 60; }
.materialize-panel { background: #fff; border-radius: 10px; padding: 20px 24px; min-width: 380px; max-width: 480px; box-shadow: 0 10px 30px rgba(0,0,0,.2); }
.materialize-panel h2 { font-size: 15px; margin: 0 0 8px; }
.materialize-hint { font-size: 12px; color: #6b7280; margin: 0 0 12px; }
</style>
