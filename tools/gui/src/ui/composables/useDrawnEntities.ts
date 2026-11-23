/**
 * Which entity each element of a diagram's picture draws, by alias, as its stable id: the element's
 * own key, or for a further occurrence the entity it stands for (`archimateOccurrences`).
 */
import { computed, ref, watch } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import { stableEntityId } from '../../domain/artifactId'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import { occurrenceItems } from '../lib/archimateOccurrences'

export function useDrawnEntities(svc: ModelService, diagramId: () => string, picture: () => LayoutGeometry | null) {
  const occurrences = ref<ReadonlyMap<string, string>>(new Map())
  watch(diagramId, async (id) => {
    if (!id) return
    const context = await Effect.runPromise(svc.getDiagramContext(id)).catch(() => null)
    const items = occurrenceItems(context?.diagram.diagram_entities ?? {})
    occurrences.value = new Map(items.map((item) => [item.id, stableEntityId(item.backing_entity_id)]))
  }, { immediate: true })

  return computed((): ReadonlyMap<string, string> => new Map((picture()?.elements ?? []).flatMap((element) => {
    const key = element.key
    return key ? [[element.alias, occurrences.value.get(key) ?? stableEntityId(key)] as const] : []
  })))
}
