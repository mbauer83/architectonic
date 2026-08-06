import { computed, ref, type Ref } from 'vue'
import type { AuthoredGrouping } from '../../domain/authoredGrouping'
import { withoutEmptyGroups } from '../../domain/authoredGrouping'

/**
 * The grouping state a diagram authoring surface needs, in one place.
 *
 * Create and edit each held their own copy of this — the same ref, the same candidate mapping, the
 * same prune-before-sending — which is how the two drifted from preview in the first place. One
 * composable means a surface that authors groupings cannot forget part of it.
 */
export function useDiagramGroupings(
  entities: Ref<readonly { artifact_id: string; name: string }[]>,
) {
  const groupings = ref<readonly AuthoredGrouping[]>([])

  /** Only what the diagram draws can be placed in a box. */
  const candidates = computed(() =>
    entities.value.map((entity) => ({ id: entity.artifact_id, label: entity.name })),
  )

  /** What goes on the wire — for a write and for the preview of it alike. */
  const forWrite = () => withoutEmptyGroups(groupings.value)

  return { groupings, candidates, forWrite }
}
