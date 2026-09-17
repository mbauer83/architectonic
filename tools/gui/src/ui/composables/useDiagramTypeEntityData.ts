import { computed, ref } from 'vue'
import type { DiagramContext } from '../../domain'
import { seededDisplayLabels, withDisplayLabel } from '../lib/archimateDisplayLabels'
import { occurrenceItems } from '../lib/archimateOccurrences'

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}

/**
 * The diagram's own data — what the diagram type stores beside the entity list — as the saved
 * base plus the edits pending on top of it.
 *
 * `onChange` is what an edit invalidates: the view resets its preview, because a preview of data
 * that has since moved is a picture of something the save will not write.
 */
export function useDiagramTypeEntityData(onChange: () => void) {
  const base = ref<Record<string, unknown>>({})
  const patch = ref<Record<string, unknown>>({})
  const typeEntityData = computed(() => ({ ...base.value, ...patch.value }))

  const mergeTypeEntityData = (delta: Record<string, unknown>): void => {
    patch.value = { ...patch.value, ...delta }
    onChange()
  }

  /**
   * Take the saved diagram as the base, and carry a hand-laid body's labels into the diagram's
   * statement as the first pending edit. Saving regenerates the body, so what the body says has to
   * be stated before then — as a pending change the preview shows and the save writes, never
   * silently.
   */
  const seedFromContext = (context: DiagramContext): void => {
    base.value = asRecord(context.diagram.diagram_entities)
    patch.value = seededDisplayLabels(
      base.value,
      context.drawn_labels,
      new Map(context.entities.map((entity) => [entity.artifact_id, entity])),
      (instanceId) => occurrenceItems(base.value).find((occ) => occ.id === instanceId)?.backing_entity_id ?? instanceId,
    )
  }

  /** The label an instance carries on this diagram; `null` lets the element speak for itself again. */
  const setInstanceLabel = (instanceId: string, label: string | null): void => {
    mergeTypeEntityData(withDisplayLabel(typeEntityData.value, instanceId, label))
  }

  return { typeEntityData, mergeTypeEntityData, seedFromContext, setInstanceLabel }
}
