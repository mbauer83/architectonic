<script setup lang="ts">
/**
 * Shared specialization picker + relationship-property fields for the connection add/edit forms.
 * The "Relationship properties" group renders ONLY when a profile is defined (`hasProfile`), so
 * create and edit behave identically and an empty schema never shows a misleading section. The
 * specialization picker is independent — choosing a specialization can itself reveal a profile.
 * Presentational only: schema/quarantine derivation lives in `useConnectionMetadata`; values and
 * their rebuild policy stay with each parent form.
 */
import type { ConnectionMetadataSchema, SpecializationGuidance } from '../../domain'
import type { SchemaQuarantine } from '../lib/schemaQuarantine'
import { specializationOptionLabel } from '../lib/specializationOptions'
import SchemaQuarantineBanner from './SchemaQuarantineBanner.vue'
import TypedPropertyInput from './TypedPropertyInput.vue'

const props = defineProps<{
  schemaInfo: ConnectionMetadataSchema | null
  specializationOptions: readonly SpecializationGuidance[]
  hasProfile: boolean
  quarantine: SchemaQuarantine
  connType: string
  specialization: string
  values: Record<string, string>
}>()
const emit = defineEmits<{
  'update:specialization': [value: string]
  'update:values': [values: Record<string, string>]
}>()

const setValue = (key: string, value: string) => emit('update:values', { ...props.values, [key]: value })
</script>

<template>
  <div class="conn-meta">
    <label
      v-if="specializationOptions.length"
      class="conn-meta__spec"
    >
      <span>Specialization</span>
      <select
        :value="specialization"
        @change="emit('update:specialization', ($event.target as HTMLSelectElement).value)"
      >
        <option value="">
          No specialization
        </option>
        <option
          v-for="option in specializationOptions"
          :key="option.slug"
          :value="option.slug"
        >
          {{ specializationOptionLabel(option) }}
        </option>
      </select>
    </label>

    <SchemaQuarantineBanner
      :quarantine="quarantine"
      :artifact-type="connType"
      :specialization="specialization"
    />

    <div
      v-if="hasProfile"
      class="conn-meta__props"
    >
      <div class="conn-meta__heading">
        Relationship properties
      </div>
      <label
        v-for="key in schemaInfo?.properties ?? []"
        :key="key"
        class="conn-meta__row"
      >
        <span>{{ key }}<b
          v-if="schemaInfo?.required.includes(key)"
          class="conn-meta__req"
        > *</b></span>
        <TypedPropertyInput
          :model-value="values[key] ?? ''"
          :descriptor="schemaInfo?.descriptors[key] ?? { type: 'string' }"
          :required="schemaInfo?.required.includes(key)"
          @update:model-value="setValue(key, $event)"
        />
      </label>
    </div>
  </div>
</template>

<style scoped>
.conn-meta { display: grid; gap: 8px; }
.conn-meta__spec, .conn-meta__row {
  display: grid; grid-template-columns: 130px 1fr; gap: 8px; font-size: 12px;
}
.conn-meta__spec { align-items: center; color: #4b5563; }
.conn-meta__row { align-items: start; color: #374151; }
.conn-meta__spec select {
  padding: 6px; border: 1px solid #d1d5db; border-radius: 5px; background: white; font: inherit;
}
.conn-meta__props { display: grid; gap: 8px; }
.conn-meta__heading { font-size: 12px; font-weight: 600; color: #374151; }
.conn-meta__req { color: #dc2626; }
</style>
