/**
 * What a diagram type may do, as the diagram-type catalogue serves it (`/api/diagram-types`): whether a
 * candidate may be drawn on a diagram of the type, and whether the type draws an element again. The one
 * reading of those answers in this app, so no view decides a capability by the spelling of a type's name.
 */
import type { DiagramTypeSummary } from './schemas/diagram-types'

/** A capability the catalogue states of each diagram type. */
export type DiagramTypeCapability = 'hosts_candidates' | 'draws_occurrences'

/** Whether *diagramType* has *capability* as *types* state it; false for a type they do not list. */
export const typeCan = (
  types: readonly DiagramTypeSummary[], diagramType: string | null | undefined, capability: DiagramTypeCapability,
): boolean => types.some((one) => one.key === diagramType && one[capability])
