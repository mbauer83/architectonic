import type { Ref } from 'vue'
import { edgeStyleKey, edgeVisualFor } from '../views/GraphExploreView.helpers'
import type { GraphEdge } from './useForceGraph'
import { useRelationNotations } from './useRelationNotations'

type EdgeStyle = Parameters<typeof edgeVisualFor>[0]
type EdgeCertainty = Parameters<typeof edgeVisualFor>[1]

/**
 * How the graph explorer draws one edge: a viewpoint's style and certainty for that connection where
 * an execution supplies them, over the ontology's notation for its relationship type.
 */
export const useGraphEdgeVisual = (
  styles: Readonly<Ref<ReadonlyMap<string, EdgeStyle>>>,
  summaries: Readonly<Ref<ReadonlyMap<string, { readonly certainty?: EdgeCertainty }>>>,
) => {
  const notations = useRelationNotations()
  return (edge: GraphEdge) => {
    const key = edgeStyleKey(edge.source, edge.target, edge.connType)
    return edgeVisualFor(
      styles.value.get(key),
      summaries.value.get(key)?.certainty ?? null,
      notations.value.get(edge.connType),
    )
  }
}
