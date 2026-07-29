/**
 * Class-B quarantine as the authoring GUI reads it.
 *
 * A (type, specialization) pair whose attribute schemata disagree has no unambiguous
 * effective schema, so the write boundary refuses every create and edit onto it. This
 * module is progressive enhancement only: it explains, before the operator fills a form
 * in, a refusal the backend guarantees regardless of whether the GUI cooperates. It is
 * never the decider — `quarantined` is the endpoint's derived read of the conflicts it
 * already returns, not a second source of truth.
 */
import type { EntitySchemaInfo } from '../../domain'

export interface SchemaQuarantine {
  readonly quarantined: boolean
  readonly conflicts: readonly string[]
}

export const NO_QUARANTINE: SchemaQuarantine = { quarantined: false, conflicts: [] }

/**
 * Older backends predate the derived flag but have always returned the conflicts it is
 * derived from, so fall back to the conflict list rather than reporting a clean pair.
 */
export const quarantineFromSchemaInfo = (info: EntitySchemaInfo): SchemaQuarantine => {
  const conflicts = info.conflicts ?? []
  return { quarantined: info.quarantined ?? conflicts.length > 0, conflicts }
}

export const quarantineHeadline = (artifactType: string, specialization: string): string =>
  specialization
    ? `Authoring is blocked for ${artifactType} «${specialization}»`
    : `Authoring is blocked for ${artifactType}`

export const QUARANTINE_REMEDY =
  'Its attribute declarations disagree, so there is no single effective schema to author '
  + 'against. Reconcile them — rename the clashing attribute, align its type, or unbind the '
  + 'profile that contributes it — then reload. Saving stays disabled until the pair resolves.'
