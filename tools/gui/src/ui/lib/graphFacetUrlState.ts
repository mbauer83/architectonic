import type { LocationQuery, LocationQueryRaw } from 'vue-router'
import type { FacetSelection } from './graphFacets'

/**
 * URL = state for the graph filter, so a filtered graph is a link somebody can send.
 *
 * One key, `?hide=`, holding `level:value` pairs — `hide=domain:motivation,entity_type:goal`.
 * Unfiltered is the ABSENCE of the key, as `?tier=` treats All, and every unrelated query key and
 * the hash survive a change, because the graph explorer already carries `?viewpoint=` and
 * `?param.*` and a filter that dropped them would break the view it is mounted on.
 *
 * A level id crosses the wire as an opaque string and is written here verbatim: nothing validates
 * it against a known set, because the known set belongs to whichever meta-ontology is loaded, and
 * a filter that rejected an unrecognised level would reject the next meta-ontology's chain.
 */

const PAIR_SEPARATOR = ','
const LEVEL_SEPARATOR = ':'

export const HIDE_KEY = 'hide'

/** Decode `?hide=` into excluded values per level. Malformed pairs are dropped, not thrown on. */
export const decodeFacetSelection = (query: LocationQuery): FacetSelection => {
  const raw = query[HIDE_KEY]
  if (typeof raw !== 'string' || raw === '') return {}
  const selection: Record<string, string[]> = {}
  for (const pair of raw.split(PAIR_SEPARATOR)) {
    const at = pair.indexOf(LEVEL_SEPARATOR)
    if (at <= 0) continue
    const level = pair.slice(0, at)
    const value = pair.slice(at + 1)
    // A value may itself contain a colon — a specialization slug is not this module's to constrain
    // — so the split is at the FIRST separator only.
    if (!value) continue
    ;(selection[level] ??= []).push(value)
  }
  return selection
}

/** The canonical encoding of a selection, or undefined when nothing is excluded. */
export const encodeFacetSelection = (selection: FacetSelection): string | undefined => {
  const pairs = Object.entries(selection)
    .flatMap(([level, values]) => values.map((value) => `${level}${LEVEL_SEPARATOR}${value}`))
    .sort()
  return pairs.length > 0 ? pairs.join(PAIR_SEPARATOR) : undefined
}

/** True when a `hide` key is present but not in canonical form, so the surface can replace it. */
export const facetSelectionNeedsNormalization = (query: LocationQuery): boolean => {
  const raw = query[HIDE_KEY]
  if (raw === undefined) return false
  return raw !== encodeFacetSelection(decodeFacetSelection(query))
}

/** The query with the selection written in, preserving unrelated keys. */
export const withFacetSelection = (
  query: LocationQuery,
  selection: FacetSelection,
): LocationQueryRaw => {
  const merged: LocationQueryRaw = { ...query }
  delete merged[HIDE_KEY]
  const encoded = encodeFacetSelection(selection)
  if (encoded !== undefined) merged[HIDE_KEY] = encoded
  return merged
}

/** The selection with one value toggled at one level. */
export const withValueToggled = (
  selection: FacetSelection,
  level: string,
  value: string,
): FacetSelection => {
  const current = selection[level] ?? []
  const next = current.includes(value)
    ? current.filter((each) => each !== value)
    : [...current, value]
  const merged: Record<string, readonly string[]> = { ...selection }
  if (next.length > 0) merged[level] = next
  else delete merged[level]
  return merged
}
