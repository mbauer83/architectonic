import type { LocationQuery, LocationQueryRaw } from 'vue-router'
import type { ViewpointExecutionResult } from '../../domain'

/**
 * URL = state for viewpoint executions. A plain `?viewpoint=<slug>&param.<name>=<value>`
 * URL is a LIVE link: it re-executes against current model and definition state and
 * silently changes as they change. A VERIFIED reference additionally pins what was seen
 * (`vpv` definition version, `vpd` definition content digest, `gen` model generation) so
 * opening it later can say "re-executed at a different generation — results may differ"
 * instead of quietly showing something else. No result archival is implied either way.
 */

const PARAM_PREFIX = 'param.'
export const VERIFIED_KEYS = ['vpv', 'vpd', 'gen'] as const

/** The live-link query for an execution: slug + its resolved parameters, nothing else —
 * stale parameters or verification pins from a previous viewpoint never leak in. */
export const executionQuery = (slug: string, parameters: Record<string, unknown>): LocationQueryRaw => {
  const query: LocationQueryRaw = { viewpoint: slug }
  for (const [name, value] of Object.entries(parameters)) {
    // A set value becomes repeated ordered keys (`scope=goal&scope=requirement`), the
    // canonical wire form the backend already parses — never a joined string that a reader
    // can't split back apart.
    query[`${PARAM_PREFIX}${name}`] = Array.isArray(value) ? value.map(String) : String(value)
  }
  return query
}

export const parametersFromQuery = (query: LocationQuery): Record<string, string | string[]> => {
  const values: Record<string, string | string[]> = {}
  for (const [key, value] of Object.entries(query)) {
    if (!key.startsWith(PARAM_PREFIX)) continue
    const name = key.slice(PARAM_PREFIX.length)
    if (Array.isArray(value)) {
      values[name] = value.filter((v): v is string => typeof v === 'string')
    } else if (typeof value === 'string') {
      values[name] = value
    }
  }
  return values
}

export interface VerifiedPins {
  readonly version: number
  readonly definitionDigest: string
  readonly generation: number | null
}

/** The verified-reference query: the live query plus the pins. */
export const verifiedReferenceQuery = (live: LocationQueryRaw, pins: VerifiedPins): LocationQueryRaw => ({
  ...live,
  vpv: String(pins.version),
  vpd: pins.definitionDigest,
  ...(pins.generation !== null ? { gen: String(pins.generation) } : {}),
})

/** Human-readable mismatch statement when a verified reference re-executed against moved
 * state — null for live links and for verified references whose state still matches. */
export const verifiedReferenceMismatch = (
  query: LocationQuery,
  result: ViewpointExecutionResult | null,
  currentDefinitionDigest: string | null,
): string | null => {
  if (result === null) return null
  const pinnedGeneration = typeof query.gen === 'string' ? query.gen : null
  const pinnedDigest = typeof query.vpd === 'string' ? query.vpd : null
  if (pinnedGeneration === null && pinnedDigest === null) return null
  const notes: string[] = []
  if (pinnedDigest !== null && currentDefinitionDigest !== null && pinnedDigest !== currentDefinitionDigest) {
    notes.push('the definition has changed since this reference was captured')
  }
  if (pinnedGeneration !== null && result.index_generation !== null && String(result.index_generation) !== pinnedGeneration) {
    notes.push(
      `re-executed at model generation ${result.index_generation} (reference captured at ${pinnedGeneration})`,
    )
  }
  if (notes.length === 0) return null
  return `Verified reference: ${notes.join('; ')} — results may differ.`
}
