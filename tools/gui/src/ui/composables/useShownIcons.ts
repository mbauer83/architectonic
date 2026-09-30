import { computed, onScopeDispose, watch, type Ref } from 'vue'
import type { ShownIcons } from '../../domain/schemas/icons'
import type { EditedInstance } from '../../ports/IconRepository'
import type { RepoError } from '../../ports/repositoryErrors'
import type { ModelService } from '../../application/ModelService'
import { useQuery } from './useQuery'

export const SHOWN_ICONS_DEBOUNCE_MS = 250

const NOTHING_SHOWN: ShownIcons = { icons: {}, pictures: {}, drawn_as: {} }

/**
 * Which icon each instance of the diagram being edited shows, as the server works it out.
 *
 * Asked rather than computed, so the chips beside the rows show exactly what the save will draw: the
 * precedence (instance, specialization, type, specialization default) and what an icon applies to are
 * the server's. The question is asked after a burst of edits settles, not per keystroke, and `useQuery`
 * discards an answer to a question that has since changed.
 */
export function useShownIcons(
  svc: Pick<ModelService, 'previewShownIcons'>,
  diagramType: Ref<string | undefined>,
  diagramEntities: Ref<Record<string, unknown>>,
  instances: Ref<readonly EditedInstance[]>,
  enabled: Ref<boolean>,
  delayMs: number = SHOWN_ICONS_DEBOUNCE_MS,
) {
  const query = useQuery<ShownIcons, RepoError>()
  let timer: ReturnType<typeof setTimeout> | null = null

  const schedule = (): void => {
    if (timer !== null) clearTimeout(timer)
    if (!enabled.value || instances.value.length === 0) {
      query.reset()
      return
    }
    timer = setTimeout(() => {
      timer = null
      query.run(svc.previewShownIcons({
        ...(diagramType.value ? { diagram_type: diagramType.value } : {}),
        diagram_entities: diagramEntities.value, instances: instances.value,
      }))
    }, delayMs)
  }

  watch([diagramType, diagramEntities, instances, enabled], schedule, { immediate: true, deep: true })
  onScopeDispose(() => { if (timer !== null) clearTimeout(timer) })

  return { shown: computed(() => query.data.value ?? NOTHING_SHOWN), error: query.errorMessage }
}
