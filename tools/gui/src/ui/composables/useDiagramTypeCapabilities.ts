import { shallowRef } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { DiagramSummary, DiagramTypeSummary } from '../../domain'
import { type DiagramTypeCapability, typeCan } from '../../domain/diagramTypeCapabilities'

type ListsTypes = Pick<ModelService, 'listDiagramTypes'>

/**
 * Whether a diagram type has a capability, as the catalogue answers once it is read. Until then, and where
 * it cannot be read, no type has any: a control that depends on one is withheld rather than offered on a
 * guess.
 */
export const useDiagramTypeCapabilities = (svc: ListsTypes) => {
  const types = shallowRef<readonly DiagramTypeSummary[]>([])
  void Effect.runPromise(svc.listDiagramTypes()).then((listed) => { types.value = listed }, () => undefined)
  return (diagramType: string | null | undefined, capability: DiagramTypeCapability): boolean =>
    typeCan(types.value, diagramType, capability)
}

/** The stored diagrams a candidate may be drawn on: those whose type the catalogue says hosts candidates. */
export const diagramsHostingCandidates = async (
  svc: ListsTypes & Pick<ModelService, 'listDiagrams'>,
): Promise<readonly DiagramSummary[]> => {
  const [listed, types] = await Promise.all([
    Effect.runPromise(svc.listDiagrams()).catch(() => null),
    Effect.runPromise(svc.listDiagramTypes()).catch((): DiagramTypeSummary[] => []),
  ])
  return (listed?.items ?? []).filter((one) => typeCan(types, one.diagram_type, 'hosts_candidates'))
}
