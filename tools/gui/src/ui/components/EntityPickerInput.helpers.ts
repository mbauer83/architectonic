/**
 * Pure helpers for EntityPickerInput fixed-level display and widen constraints.
 * Extracted for testability (no .vue import required).
 */
import type { EntityDisplayInfo, ReferenceSearchHit } from '../../domain'

export type WidenableTo = 'none' | 'domain' | 'group'

/** The picker's result-hit shape: the generic reference hit plus the model-vs-diagram
 * partition flag the dropdown's divider is rendered from. */
export type PickerHit = ReferenceSearchHit & { readonly diagram_internal: boolean }

/** Adapt an entity-display-search result item to the picker's result-hit shape. */
export function entityDisplayInfoToHit(entity: EntityDisplayInfo): PickerHit {
  return {
    artifact_id: entity.artifact_id,
    record_type: 'entity',
    name: entity.name,
    status: entity.status,
    path: '',
    artifact_type: entity.artifact_type,
    domain: entity.domain,
    diagram_internal: entity.diagram_internal,
  }
}

/** Index of the first diagram-internal hit — where the "diagram-internal" divider row is
 * rendered; −1 when every hit is a model entity (no divider). The backend guarantees the
 * partition order, so one index fully describes the split. */
export function dividerIndex(hits: readonly PickerHit[]): number {
  return hits.findIndex((hit) => hit.diagram_internal)
}

/** Whether the interactive filter stage should be shown. */
export function calcHasStageUI(
  fixedDomains: string[] | undefined,
  fixedEntityTypes: string[] | undefined,
  widenableTo: WidenableTo | undefined,
): boolean {
  if (widenableTo === 'none') return false
  return !(fixedDomains?.length && fixedEntityTypes?.length)
}

/** Whether the "← Back" navigation button should be shown. */
export function calcCanGoBack(
  currentStage: 'scope' | 'entity-type',
  fixedDomains: string[] | undefined,
  widenableTo: WidenableTo | undefined,
): boolean {
  return currentStage === 'entity-type' && !fixedDomains?.length && widenableTo !== 'none'
}

/** Whether the "Entity Types →" navigation button should be shown. */
export function calcCanGoForward(
  currentStage: 'scope' | 'entity-type',
  fixedEntityTypes: string[] | undefined,
  widenableTo: WidenableTo | undefined,
): boolean {
  return currentStage === 'scope' && !fixedEntityTypes?.length && widenableTo !== 'none'
}
