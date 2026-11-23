/**
 * Which entity each element of a diagram's picture draws, by alias, as its stable id: the element's
 * own key, or for a further occurrence the entity it stands for (`archimateOccurrences`), read from
 * the diagram context the caller already holds.
 */
import { computed } from 'vue'
import type { DiagramContext } from '../../domain'
import { stableEntityId } from '../../domain/artifactId'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import { occurrenceItems } from '../lib/archimateOccurrences'

export function useDrawnEntities(context: () => DiagramContext | null, picture: () => LayoutGeometry | null) {
  const occurrences = computed(() => new Map(occurrenceItems(context()?.diagram.diagram_entities ?? {})
    .map((item) => [item.id, stableEntityId(item.backing_entity_id)])))

  return computed((): ReadonlyMap<string, string> => new Map((picture()?.elements ?? []).flatMap((element) => {
    const key = element.key
    return key ? [[element.alias, occurrences.value.get(key) ?? stableEntityId(key)] as const] : []
  })))
}
