import { ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { CriteriaCatalog } from '../../domain'
import type { ViewpointDefinitionDraft } from '../../domain/viewpointDefinitionDraft'
import { definitionToMapping } from '../../domain/viewpointDefinitionSerialization'
import { attributeTypeTablesFromCatalog } from '../../domain/viewpointBindings'
import { failingStyleRuleIndices } from '../views/ViewpointsManagementView.helpers'

/**
 * Fork-safe validation: a dry-run persist over the fork draft; any style rule that fails
 * validation (typically an inherited rule whose attribute no longer resolves on this repo's
 * schema) is quarantined — `disabled: true`, saveable, visibly noticed — instead of
 * dead-ending the save with an error the fork author never wrote. Mutates the passed draft's
 * styling rules in place and reports how many were quarantined.
 */
export function useForkRuleQuarantine(svc: ModelService) {
  const quarantinedRuleCount = ref(0)

  const quarantineDriftedRules = async (
    draft: ViewpointDefinitionDraft,
    catalog: CriteriaCatalog,
  ): Promise<void> => {
    if (!draft.presentation) return
    const body = { definition: definitionToMapping(draft, attributeTypeTablesFromCatalog(catalog)), dry_run: true }
    const result = await Effect.runPromise(svc.createViewpointDefinition(body)).catch(() => null)
    if (!result || !draft.presentation) return
    const failing = failingStyleRuleIndices(result.issues)
    if (failing.size === 0) return
    draft.presentation.stylingRules = draft.presentation.stylingRules.map(
      (rule, index) => failing.has(index) ? { ...rule, disabled: true } : rule,
    )
    quarantinedRuleCount.value = failing.size
  }

  return { quarantinedRuleCount, quarantineDriftedRules }
}
