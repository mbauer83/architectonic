import { computed, watch, type Ref } from 'vue'
import type { DiagramTypeUiConfig, NotFoundError } from '../../domain'
import type { RepoError } from '../../ports/repositoryErrors'
import type { ModelService } from '../../application/ModelService'
import { useQuery } from './useQuery'

/**
 * The UI config of the diagram type a view is showing, fetched whenever the type changes: null until
 * it arrives, and where the type has none. A config for a type the view has since left is discarded.
 */
export function useDiagramTypeUiConfig(
  svc: Pick<ModelService, 'getDiagramTypeUiConfig'>,
  diagramType: Ref<string | null | undefined>,
): Ref<DiagramTypeUiConfig | null> {
  const query = useQuery<DiagramTypeUiConfig, RepoError | NotFoundError>()
  watch(diagramType, (type) => {
    if (type) query.run(svc.getDiagramTypeUiConfig(type))
    else query.reset()
  }, { immediate: true })
  return computed(() => query.data.value)
}
