import { ref, type Ref } from 'vue'
import { fetchRelationNotations, type RelationNotation } from '../lib/relationNotations'

/**
 * How the ontology says each relationship type is drawn, for one surface.
 *
 * One request per surface rather than per edge, and empty until it arrives, which draws a plain line
 * for a frame rather than nothing. The graph explorer and the scratchpad canvas both read it.
 */
export const useRelationNotations = (): Readonly<Ref<ReadonlyMap<string, RelationNotation>>> => {
  const notations = ref<ReadonlyMap<string, RelationNotation>>(new Map())
  void fetchRelationNotations().then((found) => { notations.value = found })
  return notations
}
