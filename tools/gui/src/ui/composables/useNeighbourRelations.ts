import { computed, ref, type Ref } from 'vue'
import { explorationFocus, relationsOfFocus } from '../lib/focusRelations'

/**
 * Whether a free exploration draws the relations between neighbours, and the relations it draws.
 *
 * Off by default: the explored entities' relations are drawn, and those between two neighbours on
 * request. Where the surface does not offer the choice — a viewpoint's population is drawn whole —
 * every loaded relation is drawn. The rule itself is `lib/focusRelations`.
 */
export const useNeighbourRelations = <E extends { readonly source: string; readonly target: string }>(input: {
  nodes: Ref<readonly { readonly id: string; readonly expanded: boolean }[]>
  edges: Ref<readonly E[]>
  rootId: Ref<string>
  offered: Readonly<Ref<boolean>>
}) => {
  const shown = ref(false)
  const drawn = computed<readonly E[]>(() =>
    input.offered.value && !shown.value
      ? relationsOfFocus(input.edges.value, explorationFocus(input.rootId.value, input.nodes.value))
      : input.edges.value,
  )
  return {
    drawn,
    /** What the toolbar's checkbox shows: whether it is offered, and whether it is checked. */
    toggle: computed(() => ({ offered: input.offered.value, shown: shown.value })),
    show: (value: boolean): void => { shown.value = value },
  }
}
