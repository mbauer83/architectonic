import type { EdgeEndMarker } from '../components/GraphCanvas.helpers'

/**
 * How each relationship type is drawn, as the ontology declares it.
 *
 * `connections.yaml` calls its `notation:` block **the single authority for arrow shape**, and
 * says why: `puml_arrow` cannot serve, because PlantUML expresses containment by nesting, so
 * composition and aggregation both spell `-->` there and their defining diamonds are lost. A
 * surface that reads the PlantUML spelling therefore draws two different relationships
 * identically — which is what the graph explorer did before this existed.
 *
 * Here rather than beside one view because there are now two consumers: the graph explorer and
 * the scratchpad canvas. The shapes are structural — no name here belongs to any ontology's
 * vocabulary — so a second meta-ontology declaring its own notation needs no code at all.
 */
export interface RelationNotation {
  line: 'solid' | 'dashed' | 'dotted'
  source: EdgeEndMarker
  target: EdgeEndMarker
}

/** Fetch every relationship type's notation. One request per surface, not one per edge. */
export const fetchRelationNotations = async (): Promise<ReadonlyMap<string, RelationNotation>> => {
  const response = await fetch('/api/relation-notations')
  if (!response.ok) return new Map()
  const body = await response.json() as { notations?: Record<string, RelationNotation> }
  return new Map(Object.entries(body.notations ?? {}))
}

/** The SVG dash pattern for a declared line style; `undefined` is a solid stroke. */
export const notationDash = (line: RelationNotation['line'] | undefined): string | undefined => {
  if (line === 'dashed') return '6 4'
  if (line === 'dotted') return '2 3'
  return undefined
}
