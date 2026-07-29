import { computed, ref } from 'vue'
import type { Ref } from 'vue'
import type { ViewpointDefinitionEnvelope } from '../../domain'
import {
  isBlankDraftValue,
  needsParameterPrompt,
  type ParameterDraft,
  parameterSignatureOf,
  parametersToWireValues,
} from '../lib/viewpointExecutionParameters'

export interface ResolvedViewpointExecution {
  readonly slug: string
  readonly parameters: Record<string, unknown>
}

/**
 * The proactive parameter-prompt gate: a definition with at least one required,
 * undefaulted parameter shows the prompt dialog before the first execution instead of
 * failing with a parameter-missing error. Every execution surface (table, exploration,
 * matrix, diagram) shares this one gate so the prompting behavior never drifts between
 * them. `onResolved` receives the slug plus wire-shaped parameters once resolved (an
 * empty object for a definition that needed no prompt) — callers decide what to actually
 * execute (a single `useViewpointExecution.execute`, or, for the diagram surface, that
 * plus a second ad-hoc SVG-render call).
 */
export function useViewpointParameterPrompt(
  onResolved: (resolved: ResolvedViewpointExecution) => void | Promise<void>,
  definitions: Ref<readonly ViewpointDefinitionEnvelope[]>,
) {
  const pendingSlug = ref<string | null>(null)
  const parameters = computed(() =>
    pendingSlug.value === null ? [] : parameterSignatureOf(definitions.value.find((d) => d.slug === pendingSlug.value)),
  )

  const run = async (slug: string, preset?: ParameterDraft): Promise<void> => {
    const signature = parameterSignatureOf(definitions.value.find((d) => d.slug === slug))
    if (needsParameterPrompt(signature)) {
      // A URL-provided preset that covers every required parameter executes directly —
      // reloading a shared link must reproduce the result, not re-open the dialog.
      const covered = signature
        .filter((parameter) => parameter.required)
        .every((parameter) => !isBlankDraftValue(preset?.[parameter.name]))
      if (preset !== undefined && covered) {
        await onResolved({ slug, parameters: parametersToWireValues(signature, preset) })
        return
      }
      pendingSlug.value = slug
      return
    }
    await onResolved({ slug, parameters: {} })
  }

  const submit = async (draft: ParameterDraft): Promise<void> => {
    const slug = pendingSlug.value
    if (slug === null) return
    const signature = parameters.value
    pendingSlug.value = null
    await onResolved({ slug, parameters: parametersToWireValues(signature, draft) })
  }

  const cancel = (): void => { pendingSlug.value = null }

  return { visible: computed(() => pendingSlug.value !== null), parameters, run, submit, cancel }
}
