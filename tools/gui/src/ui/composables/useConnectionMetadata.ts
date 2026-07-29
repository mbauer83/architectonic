import { computed, type Ref } from 'vue'
import type { AuthoringGuidance, ConnectionMetadataSchema, SpecializationGuidance } from '../../domain'
import { connectionMetadataSchema, specializationOptionsForConnectionType } from '../lib/specializationOptions'
import type { SchemaQuarantine } from '../lib/schemaQuarantine'

/**
 * Shared schema resolution for the connection add/edit forms, so the two can never drift on
 * WHEN relationship properties appear. Derives the effective metadata schema, the type's
 * specialization options, whether a profile is actually defined (the gate for showing the
 * "Relationship properties" section), and the class-B quarantine state — all as pure computeds
 * off the caller's reactive `(guidance, connectionType, specialization)`.
 */
export function useConnectionMetadata(
  guidance: Ref<AuthoringGuidance | null>,
  connectionType: Ref<string>,
  specialization: Ref<string>,
) {
  const schemaInfo = computed<ConnectionMetadataSchema | null>(() =>
    connectionMetadataSchema(guidance.value, connectionType.value, specialization.value),
  )
  const specializationOptions = computed<readonly SpecializationGuidance[]>(() =>
    specializationOptionsForConnectionType(guidance.value, connectionType.value),
  )
  // "A profile is defined" ⇔ the effective schema declares at least one property. The
  // Relationship-properties section shows iff this holds — identically on create and edit —
  // so an empty schema never renders a misleading "no properties" section.
  const hasProfile = computed(() => (schemaInfo.value?.properties.length ?? 0) > 0)
  const quarantine = computed<SchemaQuarantine>(() => ({
    quarantined: schemaInfo.value?.quarantined ?? false,
    conflicts: schemaInfo.value?.conflicts ?? [],
  }))
  return { schemaInfo, specializationOptions, hasProfile, quarantine }
}
