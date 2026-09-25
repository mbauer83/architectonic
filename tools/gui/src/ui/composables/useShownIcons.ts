import { onScopeDispose, ref, watch, type Ref } from 'vue'
import { Effect, Exit } from 'effect'
import type { ShownIcons } from '../../domain/schemas/icons'
import type { EditedInstance } from '../../ports/IconRepository'
import type { ModelService } from '../../application/ModelService'

export const SHOWN_ICONS_DEBOUNCE_MS = 250

const NOTHING_SHOWN: ShownIcons = { icons: {}, pictures: {} }

/**
 * Which icon each instance of the diagram being edited shows, as the server works it out.
 *
 * Asked rather than computed, so the chips beside the rows show exactly what the save will draw: the
 * precedence (instance, specialization, type, specialization default) and what an icon applies to are
 * the server's. The question is asked after a burst of edits settles, not per keystroke, and an answer
 * to a question that has since changed is discarded rather than shown.
 */
export function useShownIcons(
  svc: Pick<ModelService, 'previewShownIcons'>,
  diagramEntities: Ref<Record<string, unknown>>,
  instances: Ref<readonly EditedInstance[]>,
  enabled: Ref<boolean>,
  delayMs: number = SHOWN_ICONS_DEBOUNCE_MS,
) {
  const shown = ref<ShownIcons>(NOTHING_SHOWN)
  const error = ref<string | null>(null)
  let asked = 0
  let timer: ReturnType<typeof setTimeout> | null = null

  const ask = async (): Promise<void> => {
    const question = ++asked
    const exit = await Effect.runPromiseExit(svc.previewShownIcons({
      diagram_entities: diagramEntities.value, instances: instances.value,
    }))
    if (question !== asked) return
    if (Exit.isSuccess(exit)) {
      shown.value = exit.value
      error.value = null
    } else {
      error.value = 'Could not work out which icons are shown'
    }
  }

  const schedule = (): void => {
    if (timer !== null) clearTimeout(timer)
    if (!enabled.value || instances.value.length === 0) {
      asked += 1
      shown.value = NOTHING_SHOWN
      return
    }
    timer = setTimeout(() => { timer = null; void ask() }, delayMs)
  }

  watch([diagramEntities, instances, enabled], schedule, { immediate: true, deep: true })
  onScopeDispose(() => { if (timer !== null) clearTimeout(timer) })

  return { shown, error }
}
