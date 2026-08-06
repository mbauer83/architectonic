import { computed, ref, watch, type Ref } from 'vue'
import type { AuthoredGrouping } from '../../domain/authoredGrouping'
import {
  groupLabelByMember, membersOfGroup, withMemberBeside, withoutEmptyGroups,
} from '../../domain/authoredGrouping'
import { occurrenceOrdinal, occurrencesOf } from '../lib/archimateOccurrences'

/**
 * The grouping state a diagram authoring surface needs, in one place.
 *
 * Create and edit each held their own copy of this — the same ref, the same candidate mapping, the
 * same prune-before-sending — which is how the two drifted from preview in the first place. One
 * composable means a surface that authors groupings cannot forget part of it.
 */
export function useDiagramGroupings(
  entities: Ref<readonly { artifact_id: string; name: string }[]>,
  diagramEntities?: Ref<Record<string, unknown>>,
) {
  const groupings = ref<readonly AuthoredGrouping[]>([])

  /**
   * Only what the diagram draws can be placed in a box — every *drawing* of it, not every entity.
   *
   * A box holds one drawing, so an entity drawn twice offers two candidates and a reader can tell
   * which copy a box contains.
   */
  const candidates = computed(() =>
    entities.value.flatMap((entity) => [
      { id: entity.artifact_id, label: entity.name },
      ...occurrencesOf(diagramEntities?.value ?? {}, entity.artifact_id).map((occurrence, index) => ({
        id: occurrence.id,
        label: `${entity.name} (${occurrenceOrdinal(index)})`,
      })),
    ]),
  )

  /** Which box holds each drawing — what an Included Entities row shows beside its name. */
  const labelOfDrawing = (drawingId: string): string | undefined =>
    groupLabelByMember(groupings.value).get(drawingId)

  /** Put a drawing in the box that holds *hostId*; a no-op when the host is in no box. */
  const placeBeside = (hostId: string, memberId: string): void => {
    groupings.value = withMemberBeside(groupings.value, hostId, memberId)
  }

  /** The drawings one box holds, so a new member can be wired to what is already inside it. */
  const membersOf = (groupIndex: number): readonly string[] =>
    membersOfGroup(groupings.value[groupIndex])

  /** Put a drawing in one box. Adding one it already holds says nothing, so it is left alone. */
  const addMember = (groupIndex: number, memberId: string): void => {
    groupings.value = groupings.value.map((group, index) =>
      index !== groupIndex || group['entity-ids'].includes(memberId)
        ? group
        : { ...group, 'entity-ids': [...group['entity-ids'], memberId] },
    )
  }

  /**
   * Take the boxes the diagram already draws, once.
   *
   * An editor that never saw them would replace them on its next save, so this runs before any
   * edit — and only the first time, or reloading would discard edits in progress.
   */
  const seedOnce = (source: Ref<{ authored_groupings?: readonly AuthoredGrouping[] | null } | null>): void => {
    const seeded = ref(false)
    watch(source, (detail) => {
      if (!detail || seeded.value) return
      groupings.value = detail.authored_groupings ?? []
      seeded.value = true
    }, { immediate: true })
  }

  /** What goes on the wire — for a write and for the preview of it alike. */
  const forWrite = () => withoutEmptyGroups(groupings.value)

  return {
    groupings, candidates, forWrite, addMember, labelOfDrawing, membersOf, placeBeside, seedOnce,
  }
}
