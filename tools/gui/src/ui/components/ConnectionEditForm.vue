<script setup lang="ts">
import { computed, inject, ref, toRef, watch } from 'vue'
import { Exit } from 'effect'
import type { AuthoringGuidance, ConnectionRowView, WriteResult } from '../../domain'
import type { RepoError } from '../../ports/ModelRepository'
import { modelServiceKey } from '../keys'
import { useMutation } from '../composables/useMutation'
import { useConnectionMetadata } from '../composables/useConnectionMetadata'
import { metadataInputValue, metadataWireValues } from '../lib/connectionMetadataValues'
import ConnectionMetadataFields from './ConnectionMetadataFields.vue'

const props = defineProps<{ connection: ConnectionRowView; guidance: AuthoringGuidance | null }>()
const emit = defineEmits<{ saved: []; cancel: [] }>()
const svc = inject(modelServiceKey)!

const description = ref(props.connection.content_text ?? '')
const sourceMultiplicity = ref(props.connection.src_multiplicity ?? '')
const targetMultiplicity = ref(props.connection.tgt_multiplicity ?? '')
const specialization = ref(props.connection.specializations[0] ?? '')
const mutation = useMutation<WriteResult, RepoError>()

const metadataValues = ref<Record<string, string>>(
  Object.fromEntries(
    Object.entries(props.connection.metadata ?? {}).map(([key, value]) => [key, metadataInputValue(value)]),
  ),
)
const connType = computed(() => props.connection.conn_type)
const { schemaInfo, specializationOptions, hasProfile, quarantine } = useConnectionMetadata(
  toRef(props, 'guidance'), connType, specialization,
)

// Edit MERGES: a specialization change keeps the values the user has already typed and adds any
// newly-declared key at its default — the base type is fixed, so specializations only refine.
watch(schemaInfo, (info) => {
  const next = { ...metadataValues.value }
  for (const key of info?.properties ?? []) {
    if (!(key in next)) next[key] = info?.descriptors[key]?.default ?? ''
  }
  metadataValues.value = next
}, { immediate: true })

const requiredMissing = computed(() =>
  (schemaInfo.value?.required ?? []).some((key) => !metadataValues.value[key]?.trim()),
)

const MULTIPLICITY_RE = /^\d+$|^\d+\.\.\d+$|^\d+\.\.\*$|^\*$/
const multiplicityError = (value: string) =>
  value.trim() && !MULTIPLICITY_RE.test(value.trim()) ? 'Use n, n..m, n..*, or *' : ''
const sourceError = computed(() => multiplicityError(sourceMultiplicity.value))
const targetError = computed(() => multiplicityError(targetMultiplicity.value))
const blocked = computed(() =>
  mutation.running.value || quarantine.value.quarantined || requiredMissing.value
  || !!sourceError.value || !!targetError.value,
)
const error = computed(() =>
  mutation.result.value?.wrote === false
    ? (mutation.result.value.content ?? 'Verification failed')
    : mutation.errorMessage.value,
)

const save = () => {
  if (blocked.value) return
  const metadata = metadataWireValues(
    metadataValues.value,
    schemaInfo.value?.descriptors ?? {},
    props.connection.metadata ?? {},
  )
  // Identity is the connection's own composite id, which the read surface already gave us.
  void mutation.run(svc.editConnection(props.connection.artifact_id, {
    description: description.value.trim(),
    src_multiplicity: sourceMultiplicity.value.trim(),
    tgt_multiplicity: targetMultiplicity.value.trim(),
    specialization: specialization.value,
    metadata,
    dry_run: false,
  })).then((exit) => Exit.match(exit, {
    onSuccess: (result) => { if (result.wrote) emit('saved') },
    onFailure: () => {},
  }))
}
</script>

<template>
  <div class="edit-form">
    <label class="field-label">
      Description
      <textarea
        v-model="description"
        class="description"
        rows="2"
        placeholder="Optional relationship description"
      />
    </label>
    <div class="multiplicity-row">
      <label>Source <input
        v-model="sourceMultiplicity"
        class="multiplicity"
        placeholder="e.g. 1..*"
        maxlength="20"
      ></label>
      <span aria-hidden="true">→</span>
      <label>Target <input
        v-model="targetMultiplicity"
        class="multiplicity"
        placeholder="e.g. 0..*"
        maxlength="20"
      ></label>
    </div>
    <div
      v-if="sourceError || targetError"
      class="error"
    >
      {{ sourceError || targetError }}
    </div>

    <ConnectionMetadataFields
      v-model:specialization="specialization"
      v-model:values="metadataValues"
      class="properties"
      :schema-info="schemaInfo"
      :specialization-options="specializationOptions"
      :has-profile="hasProfile"
      :quarantine="quarantine"
      :conn-type="connection.conn_type"
    />

    <div class="actions">
      <button
        class="cancel"
        type="button"
        @click="emit('cancel')"
      >
        Cancel
      </button>
      <button
        class="save"
        type="button"
        :disabled="blocked"
        @click="save"
      >
        Save relationship
      </button>
    </div>
    <div
      v-if="error"
      class="error"
    >
      {{ error }}
    </div>
  </div>
</template>

<style scoped>
.edit-form { margin: 4px 0 8px; padding: 10px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; }
.field-label { display: grid; gap: 4px; font-size: 11px; color: #4b5563; }
.description { resize: vertical; padding: 6px 8px; border: 1px solid #d1d5db; border-radius: 5px; font: inherit; }
.multiplicity-row { display: flex; gap: 8px; align-items: end; margin-top: 8px; color: #9ca3af; }
.multiplicity-row label { display: grid; gap: 3px; font-size: 11px; color: #4b5563; }
.multiplicity { width: 96px; padding: 5px 7px; border: 1px solid #d1d5db; border-radius: 5px; font: 12px monospace; }
.properties { margin-top: 10px; border-top: 1px solid #e5e7eb; padding-top: 8px; }
.error { color: #dc2626; }
.actions { display: flex; justify-content: flex-end; gap: 6px; margin-top: 10px; }
.actions button { padding: 6px 12px; border-radius: 5px; cursor: pointer; }
.cancel { border: 1px solid #d1d5db; background: white; color: #374151; }
.save { border: 0; background: #2563eb; color: white; }
.save:disabled { opacity: .5; cursor: not-allowed; }
.error { margin-top: 6px; font-size: 12px; }
</style>
