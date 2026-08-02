import { computed, ref } from 'vue'
import type { Ref } from 'vue'
import type { ViewpointDefinitionEnvelope } from '../../domain'
import {
  initialParameterDraft,
  missingRequiredParameters,
  type ParameterDraft,
  parameterSignatureOf,
  parametersToWireValues,
} from '../lib/viewpointExecutionParameters'

export interface ResolvedViewpointExecution {
  readonly slug: string
  readonly parameters: Record<string, unknown>
}

/**
 * The proactive parameter-prompt gate: a definition with a required parameter that no
 * default and no caller-supplied preset covers shows the prompt dialog before the first
 * execution instead of failing with a parameter-missing error. Every execution surface (table,
 * exploration,
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

  /**
   * Execute `slug`, prompting only when a required parameter has no value from any source.
   *
   * The preset is layered over the declared defaults, so "covered" means covered by either —
   * and the values that reach the wire are the ones the caller asked for. An earlier version
   * consulted the preset ONLY when some required parameter was undefaulted, and resolved with
   * an empty `{}` otherwise: for a definition whose parameters are all optional or defaulted,
   * every `?param.` value in a shared link was silently discarded, and the surfaces that
   * rewrite the address from the resolved execution then erased them from it too.
   */
  const run = async (slug: string, preset?: ParameterDraft): Promise<void> => {
    const signature = parameterSignatureOf(definitions.value.find((d) => d.slug === slug))
    const draft = { ...initialParameterDraft(signature), ...preset }
    if (missingRequiredParameters(signature, draft).length > 0) {
      pendingSlug.value = slug
      return
    }
    // No preset: nothing was asked for, so nothing is asserted. The server applies the same
    // declared defaults, and an address naming values the caller never chose is noise.
    await onResolved({ slug, parameters: preset === undefined ? {} : parametersToWireValues(signature, draft) })
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
