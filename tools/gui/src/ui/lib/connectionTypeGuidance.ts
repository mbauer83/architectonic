import type { AuthoringGuidance } from '../../domain'

/** When to create a relationship of one type, and when something else fits better. */
export interface ConnectionCreationGuidance {
  readonly createWhen: string
  readonly neverCreateWhen: string
}

/**
 * Creation guidance for one connection type, from the `connection_types` block of
 * `GET /api/authoring-guidance`. Null when the type is absent from the payload or carries no text
 * — guidance ships empty until an import has run, and an empty note must not render as a hint that
 * says nothing.
 *
 * Deliberately consumed by the wizards only: a guided pass is where a relationship choice is being
 * made and the framing helps, whereas the ordinary connection forms are for someone who has already
 * decided.
 */
export function connectionCreationGuidance(
  guidance: AuthoringGuidance | null,
  connectionType: string,
): ConnectionCreationGuidance | null {
  const entry = guidance?.connection_types?.find((candidate) => candidate.name === connectionType)
  const createWhen = entry?.create_when?.trim() ?? ''
  const neverCreateWhen = entry?.never_create_when?.trim() ?? ''
  return createWhen || neverCreateWhen ? { createWhen, neverCreateWhen } : null
}

/** Display label for a connection type in guidance surfaces, e.g. `archimate-serving` → `serving`. */
export function connectionTypeLabel(connectionType: string): string {
  return connectionType.replace(/^archimate-/, '')
}
