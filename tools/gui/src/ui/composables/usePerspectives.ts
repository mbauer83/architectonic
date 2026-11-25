/**
 * The perspectives offered to whoever writes stressors, read from the server once per page load:
 * they are shipped data, the same for every analysis. A read that fails leaves the line empty, and
 * writing a stressor never depends on it.
 */
import { shallowRef } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { PerspectiveFramework } from '../../domain/schemas/stressEvaluation'

const frameworks = shallowRef<readonly PerspectiveFramework[]>([])
let requested = false

export function usePerspectives(svc: Pick<ModelService, 'listStressPerspectives'>) {
  if (!requested) {
    requested = true
    void Effect.runPromise(svc.listStressPerspectives())
      .then((read) => { frameworks.value = read.frameworks })
      .catch(() => { requested = false })
  }
  return frameworks
}
