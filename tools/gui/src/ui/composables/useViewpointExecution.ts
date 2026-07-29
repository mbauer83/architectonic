import { ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { ViewpointExecutionRequest, ViewpointExecutionResult, ViewpointProjection } from '../../domain'
import { extractTypedApiError, readErrorMessage, type TypedApiError } from '../lib/errors'

/**
 * Fetches a viewpoint's fixed content and its styled repository projection together — the
 * one data source every execution representation (exploration, table, matrix, diagram)
 * builds on, so they can never disagree about what a viewpoint returned.
 */
export function useViewpointExecution(svc: ModelService) {
  const result = ref<ViewpointExecutionResult | null>(null)
  const projection = ref<ViewpointProjection | null>(null)
  const loading = ref(false)
  const errorMessage = ref<string | null>(null)
  const typedError = ref<TypedApiError | null>(null)
  let lastParams: ViewpointExecutionRequest | null = null

  const execute = async (params: ViewpointExecutionRequest): Promise<void> => {
    lastParams = params
    loading.value = true
    errorMessage.value = null
    typedError.value = null
    try {
      const [contentResult, projectionResult] = await Promise.all([
        Effect.runPromise(svc.executeViewpoint(params)),
        Effect.runPromise(svc.executeViewpointProjection(params)),
      ])
      result.value = contentResult
      projection.value = projectionResult
    } catch (reason) {
      errorMessage.value = readErrorMessage(reason)
      typedError.value = extractTypedApiError(reason)
      result.value = null
      projection.value = null
    } finally {
      loading.value = false
    }
  }

  const rerun = (): Promise<void> => (lastParams ? execute(lastParams) : Promise.resolve())

  const clear = (): void => {
    result.value = null
    projection.value = null
    errorMessage.value = null
    typedError.value = null
    lastParams = null
  }

  return { result, projection, loading, errorMessage, typedError, execute, rerun, clear }
}
