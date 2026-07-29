import type { AuthoringGuidance, ConnectionMetadataSchema, SpecializationGuidance } from '../../domain'

/**
 * Available specializations for one entity type, sourced from the `entity_types[].specializations`
 * block `artifact_authoring_guidance`/`GET /api/authoring-guidance` returns for that type — the
 * same guidance payload the create/edit forms already fetch for attribute schemas, so the picker
 * never needs its own round trip beyond a guidance call already scoped to the one type.
 */
export function specializationOptionsForEntityType(
  guidance: AuthoringGuidance | null,
  entityType: string,
): readonly SpecializationGuidance[] {
  if (!guidance?.entity_types) return []
  const entry = guidance.entity_types.find((e) => e.name === entityType)
  return entry?.specializations ?? []
}

/**
 * Available specializations for one connection type, sourced from the top-level
 * `connection_types` block. A type can appear solely because it declares a base metadata
 * schema; an empty specializations list therefore means "none declared".
 */
export function specializationOptionsForConnectionType(
  guidance: AuthoringGuidance | null,
  connectionType: string,
): readonly SpecializationGuidance[] {
  if (!guidance?.connection_types) return []
  const entry = guidance.connection_types.find((e) => e.name === connectionType)
  return entry?.specializations ?? []
}

/**
 * The effective metadata schema for one (connection type, specialization) pair. Falls back
 * to the connection type's own schema when no specialization is selected, and to `null`
 * when the payload carries none (an older backend, or one with no repository root) — the
 * caller then renders no typed fields rather than inventing an empty schema.
 */
export function connectionMetadataSchema(
  guidance: AuthoringGuidance | null,
  connectionType: string,
  specializationSlug: string,
): ConnectionMetadataSchema | null {
  const entry = guidance?.connection_types?.find((e) => e.name === connectionType)
  if (!entry) return null
  if (!specializationSlug) return entry.metadata_schema ?? null
  const spec = entry.specializations.find((s) => s.slug === specializationSlug)
  return spec?.metadata_schema ?? entry.metadata_schema ?? null
}

/** Display label for a specialization option, e.g. for a `<select>`'s option text. */
export function specializationOptionLabel(spec: SpecializationGuidance): string {
  return spec.name || spec.slug
}
